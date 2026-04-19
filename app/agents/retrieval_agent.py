"""
Upgraded retrieval agent — full Advanced RAG pipeline.

Pipeline:
  1. Conversation-aware rewrite     (standalone query)
  2. Query expansion                (rewrite + multi-query + HyDE)
  3. Retrieval per query variant    (BM25 + vector for each)
  4. RRF fusion                     (merge all result lists)
  5. Parent-child expansion         (child → parent context)
  6. Contextual compression         (filter noise per parent)
  7. Jina Reranker                  (final ranking on parent content)
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
from app.agents.state import AgentState
from app.retrieval.bm25_retriever      import bm25_retriever
from app.retrieval.vector_retriever    import search as vector_search
from app.retrieval.hybrid_retriever    import reciprocal_rank_fusion
from app.retrieval.query_processor     import process_query, QueryBundle
from app.retrieval.parent_store        import get_parents_batch
from app.retrieval.contextual_compressor import compress_chunks
from app.retrieval.reranker            import rerank
from app.redis_client import get_redis

log = logging.getLogger(__name__)

CACHE_TTL  = 300   # 5 min query cache
TOP_K_RAW  = 15    # results per query variant before merge
TOP_K_FUSE = 20    # after RRF before rerank
TOP_N_FINAL = 5    # after rerank


async def retrieval_agent(state: AgentState) -> AgentState:
    cid = state["conversation_id"]
    state.setdefault("agent_trace", {})

    if not state.get("has_documents"):
        state.update({"fused_chunks": [], "bm25_results": [],
                      "vector_results": [], "reranked_chunks": []})
        state["agent_trace"]["retrieval"] = "no_documents"
        return state

    # ── Cache check ───────────────────────────────────────────────────────────
    query_hash = hashlib.md5(
        f"{state['query']}::{json.dumps(state.get('history', [])[-2:])}"
        .encode()
    ).hexdigest()
    cache_key = f"rag:query:conv:{cid}:{query_hash}"
    redis     = await get_redis()
    cached    = await redis.get(cache_key)

    if cached:
        payload = json.loads(cached)
        state["reranked_chunks"]            = payload["chunks"]
        state["fused_chunks"]               = payload["chunks"]
        state["agent_trace"]["retrieval"]   = "cache_hit"
        return state

    # ── Step 1–2: Query processing ────────────────────────────────────────────
    bundle: QueryBundle = await process_query(
        query=state["query"],
        history=state.get("history", []),
        use_rewrite=True,
        use_multi_query=True,
        use_hyde=True,
        n_variants=3,
    )
    state["agent_trace"]["query_processing"] = bundle.to_dict()

    # ── Step 3: Retrieval per variant ─────────────────────────────────────────
    all_result_lists: list[list[dict]] = []
    queries = bundle.all_queries()

    # BM25: run on standalone only (BM25 doesn't benefit from HyDE)
    bm25_res = await bm25_retriever.search(bundle.standalone, TOP_K_RAW, cid)
    if bm25_res:
        all_result_lists.append(bm25_res)

    # Vector: run on all query variants + HyDE in parallel
    async def _vector(q: str, hyde: str | None = None):
        return await vector_search(q, TOP_K_RAW, cid, hyde_text=hyde)

    vector_tasks = [_vector(q) for q in queries]
    # Extra: HyDE-based vector search
    vector_tasks.append(_vector(bundle.standalone, hyde=bundle.hyde_text))

    vector_results = await asyncio.gather(*vector_tasks, return_exceptions=True)
    for res in vector_results:
        if isinstance(res, list) and res:
            all_result_lists.append(res)

    if not all_result_lists:
        state["reranked_chunks"] = []
        state["agent_trace"]["retrieval"] = "no_results"
        return state

    # ── Step 4: RRF fusion ────────────────────────────────────────────────────
    fused_children = reciprocal_rank_fusion(all_result_lists)[:TOP_K_FUSE]
    state["fused_chunks"] = fused_children

    # ── Step 5: Parent-child expansion ────────────────────────────────────────
    parent_ids = list({
        c["metadata"].get("parent_id", "")
        for c in fused_children
        if c["metadata"].get("parent_id")
    })

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        parent_map = await get_parents_batch(cid, parent_ids, db=db)

    # Build enriched chunks using parent content
    # Deduplicate by parent_id (multiple children → one parent)
    seen_parents: set[str] = set()
    expanded: list[dict]   = []

    for child in fused_children:
        pid = child["metadata"].get("parent_id", "")
        if pid and pid not in seen_parents and pid in parent_map:
            parent = parent_map[pid]
            seen_parents.add(pid)
            expanded.append({
                **child,
                "content":      parent["content"],   # use parent (larger) content
                "child_content": child["content"],   # keep child for reference
                "parent_id":    pid,
            })
        elif not pid:
            # No parent_id — use child as-is (backward compat)
            expanded.append(child)

    if not expanded:
        # Fallback: use children directly
        expanded = fused_children[:TOP_N_FINAL]

    state["agent_trace"]["parent_expansion"] = {
        "children_retrieved": len(fused_children),
        "unique_parents":     len(seen_parents),
        "expanded":           len(expanded),
    }

    # ── Step 6: Contextual compression ───────────────────────────────────────
    try:
        compressed = await compress_chunks(bundle.standalone, expanded[:10])
        state["agent_trace"]["compression"] = {
            "before_avg_len": int(sum(len(c["content"]) for c in expanded[:10]) / max(1, len(expanded[:10]))),
            "after_avg_len":  int(sum(len(c["content"]) for c in compressed) / max(1, len(compressed))),
        }
    except Exception as e:
        log.warning("Compression failed", extra={"error": str(e)})
        compressed = expanded[:10]

    # ── Step 7: Jina Reranker ─────────────────────────────────────────────────
    try:
        reranked = await rerank(bundle.standalone, compressed)
        final    = reranked[:TOP_N_FINAL]
    except Exception as e:
        log.warning("Reranker failed", extra={"error": str(e)})
        final = compressed[:TOP_N_FINAL]

    state["reranked_chunks"] = final
    state["agent_trace"]["retrieval"] = {
        "query_variants":  len(queries),
        "result_lists":    len(all_result_lists),
        "fused_children":  len(fused_children),
        "after_expansion": len(expanded),
        "after_compress":  len(compressed),
        "final":           len(final),
    }

    # ── Cache result ─────────────────────────────────────────────────────────
    await redis.setex(cache_key, CACHE_TTL, json.dumps({"chunks": final}))

    return state
