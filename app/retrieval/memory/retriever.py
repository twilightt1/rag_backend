"""
Phase 3 — ``MemoryRetriever``: the orchestrator for personal-context recall.

Pipeline (one call to :py:meth:`MemoryRetriever.recall`):

    1. Fetch personal context (pinned + last 7 days + last 20).
    2. LLM rewrite the query + extract entities (1 call; best-effort).
    3. Embed the rewritten query (1 call; falls back to original).
    4. Vector search in ChromaDB (top_k * 3 for rerank headroom).
    5. Hydrate the top candidates with full ``Memory`` rows from Postgres,
       including ``entity_links`` (so we can apply entity boost).
    6. Apply entity_boost + time_decay to each candidate.
    7. Sort by combined score, return top_k.
    8. Build the ``RecallTrace`` with timings + fallbacks used.

Every step degrades gracefully. The worst case (LLM down + ChromaDB
down + no context) still returns a 200 with an empty ``results`` list
and a trace indicating what was attempted.
"""
from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entity import MemoryEntity
from app.models.memory import Memory
from app.retrieval.embedder import embed_query
from app.retrieval.memory.context import fetch_personal_context
from app.retrieval.memory.query_rewriter import rewrite_query
from app.retrieval.memory.scoring import entity_boost, time_decay_score
from app.retrieval.memory.vector_store import search_memories
from app.schemas.Orivory import (
    MemoryResponse,
    MemoryWithScore,
    RecallResponse,
    RecallTrace,
)

log = logging.getLogger(__name__)


class MemoryRetriever:
    """High-level orchestrator. One instance per (db, user) pair."""

    def __init__(
        self,
        db: AsyncSession,
        user_id: UUID,
        *,
        half_life_days: float = 30.0,
        entity_boost_per_match: float = 0.3,
        entity_boost_max: float = 1.0,
        rerank_factor: int = 3,
        decay_floor: float = 0.1,
    ) -> None:
        self.db = db
        self.user_id = user_id
        self.half_life_days = half_life_days
        self.entity_boost_per_match = entity_boost_per_match
        self.entity_boost_max = entity_boost_max
        self.rerank_factor = rerank_factor
        self.decay_floor = decay_floor

    # ── main entry point ─────────────────────────────────────────────────

    async def recall(
        self,
        query: str,
        top_k: int = 10,
        include_personal_context: bool = True,
    ) -> RecallResponse:
        """Run the full recall pipeline and return a ``RecallResponse``."""
        t0 = time.perf_counter()

        # 1) Personal context
        context: list[Memory] = []
        if include_personal_context:
            try:
                context = await fetch_personal_context(self.db, self.user_id)
            except Exception as e:
                log.warning("fetch_personal_context failed", extra={"error": str(e)})

        # 2) LLM rewrite + entity extraction
        rewrite_result = await rewrite_query(query, context=context)
        rewritten = rewrite_result["rewritten_query"]
        entities = rewrite_result["entities"]
        llm_fallback = bool(rewrite_result.get("_fallback_used"))
        llm_reasoning = rewrite_result.get("reasoning") or None

        # Lowercased entity names for matching
        query_entity_names: set[str] = {e["name"].lower() for e in entities}

        # 3) Embed (use rewritten if LLM succeeded, else original)
        try:
            embedding = await embed_query(rewritten if not llm_fallback else query)
        except Exception as e:
            log.error("embed_query failed", extra={"error": str(e)})
            return self._empty_response(
                query, rewritten, entities, llm_fallback, llm_reasoning,
                context if include_personal_context else None,
                t0, reason=f"embedding_failed:{e}",
            )

        # 4) Vector search (top_k * rerank_factor for headroom)
        try:
            candidates = await search_memories(
                embedding,
                user_id=str(self.user_id),
                top_k=top_k * self.rerank_factor,
            )
        except Exception as e:
            log.error("search_memories failed", extra={"error": str(e)})
            candidates = []

        num_candidates = len(candidates)

        # 5) Hydrate from Postgres (with entity_links)
        if candidates:
            memory_ids = [UUID(c["memory_id"]) for c in candidates]
            hydrated = await self._hydrate(memory_ids)
        else:
            hydrated = {}

        # 6) Score: entity_boost + time_decay
        scored: list[tuple[Memory, float, list[str]]] = []
        for cand in candidates:
            mid = cand["memory_id"]
            memory = hydrated.get(mid)
            if memory is None:
                # Memory was deleted from PG but still in Chroma.
                log.debug("Skipping stale Chroma candidate", extra={"memory_id": mid})
                continue

            mem_entity_names: set[str] = {
                link.entity.name.lower()
                for link in (memory.entity_links or [])
                if link.entity is not None and link.entity.name
            }

            base_score = float(cand["score"])

            # Entity boost first
            score_after_boost, boost_reasons = entity_boost(
                base_score,
                mem_entity_names,
                query_entity_names,
                boost_per_match=self.entity_boost_per_match,
                max_boost=self.entity_boost_max,
            )

            # Then time-decay
            final_score, decay_reasons = time_decay_score(
                score_after_boost,
                captured_at=memory.captured_at,
                salience=float(memory.salience or 0.5),
                pinned=bool(memory.pinned),
                half_life_days=self.half_life_days,
                decay_floor=self.decay_floor,
            )

            reasons = boost_reasons + decay_reasons
            scored.append((memory, final_score, reasons))

        # 7) Sort by score desc, take top_k
        scored.sort(key=lambda t: t[1], reverse=True)
        top = scored[:top_k]

        # 8) Build response
        results: list[MemoryWithScore] = []
        for memory, score, reasons in top:
            base = _memory_response(memory)
            results.append(
                MemoryWithScore(
                    **base.model_dump(),
                    score=round(score, 6),
                    match_reasons=reasons,
                )
            )

        latency_ms = (time.perf_counter() - t0) * 1000.0
        trace = RecallTrace(
            rewritten_query=rewritten,
            entities=entities,
            latency_ms=round(latency_ms, 2),
            num_candidates=num_candidates,
            num_results=len(results),
            used_personal_context=bool(include_personal_context and context),
            llm_fallback=llm_fallback,
            llm_reasoning=llm_reasoning,
            half_life_days=self.half_life_days,
        )
        return RecallResponse(
            results=results,
            personal_context=[_memory_response(m) for m in context]
                             if include_personal_context else None,
            trace=trace,
        )

    # ── helpers ─────────────────────────────────────────────────────────

    async def _hydrate(self, memory_ids: list[UUID]) -> dict[str, Memory]:
        """Fetch Memory rows + entity_links in one query, keyed by id (str)."""
        if not memory_ids:
            return {}
        stmt = (
            select(Memory)
            .where(Memory.id.in_(memory_ids), Memory.user_id == self.user_id)
            .options(selectinload(Memory.entity_links).selectinload(MemoryEntity.entity))
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return {str(m.id): m for m in rows}

    def _empty_response(
        self,
        query: str,
        rewritten: str,
        entities: list[dict],
        llm_fallback: bool,
        llm_reasoning: str | None,
        context: list[Memory] | None,
        t0: float,
        reason: str,
    ) -> RecallResponse:
        log.info("Returning empty recall", extra={"reason": reason})
        latency_ms = (time.perf_counter() - t0) * 1000.0
        trace = RecallTrace(
            rewritten_query=rewritten,
            entities=entities,
            latency_ms=round(latency_ms, 2),
            num_candidates=0,
            num_results=0,
            used_personal_context=bool(context),
            llm_fallback=llm_fallback,
            llm_reasoning=llm_reasoning,
            half_life_days=self.half_life_days,
        )
        return RecallResponse(
            results=[],
            personal_context=[_memory_response(m) for m in context]
                             if context else None,
            trace=trace,
        )


def _memory_response(memory: Memory) -> MemoryResponse:
    """Map ORM Memory.extra_metadata to API field `metadata`."""
    return MemoryResponse(
        id=memory.id,
        user_id=memory.user_id,
        parent_id=memory.parent_id,
        source_type=memory.source_type,
        source_ref=memory.source_ref,
        source_url=memory.source_url,
        title=memory.title,
        content=memory.content,
        summary=memory.summary,
        tags=memory.tags or [],
        salience=memory.salience,
        pinned=memory.pinned,
        recall_count=memory.recall_count,
        last_used_at=memory.last_used_at,
        captured_at=memory.captured_at,
        indexed_at=memory.indexed_at,
        updated_at=memory.updated_at,
        metadata=getattr(memory, "extra_metadata", getattr(memory, "metadata", {})) or {},
    )
