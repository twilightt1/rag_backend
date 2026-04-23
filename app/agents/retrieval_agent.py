"""
Upgraded retrieval agent — full Advanced RAG pipeline.

Pipeline:
  1. Retrieval per query variant (from router)    (BM25 + vector for each)
  2. RRF fusion                                   (merge all result lists)
  3. Parent-child expansion                       (child → parent context)
  4. Jina Reranker                                (final ranking on parent content)
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
from app.retrieval.parent_store        import get_parents_batch
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

    # ── Step 1: Retrieval per variant ─────────────────────────────────────────
    all_result_lists: list[list[dict]] = []

    # We get variants from the router now
    standalone = state.get("rewritten_query", state["query"])
    queries = state.get("search_variants", [])
    if standalone not in queries:
        queries.insert(0, standalone)

    # BM25: run on standalone only
    bm25_res = await bm25_retriever.search(standalone, TOP_K_RAW, cid)
    if bm25_res:
        all_result_lists.append(bm25_res)

    # Vector: run on all query variants in parallel
    async def _vector(q: str):
        return await vector_search(q, TOP_K_RAW, cid)

    vector_tasks = [_vector(q) for q in queries]
    vector_results = await asyncio.gather(*vector_tasks, return_exceptions=True)
    for res in vector_results:
        if isinstance(res, list) and res:
            all_result_lists.append(res)

    if not all_result_lists:
        state["reranked_chunks"] = []
        state["agent_trace"]["retrieval"] = "no_results"
        return state

    # ── Step 2: RRF fusion ────────────────────────────────────────────────────
    fused_children = reciprocal_rank_fusion(all_result_lists)[:TOP_K_FUSE]
    state["fused_chunks"] = fused_children

    # ── Step 3: Parent-child expansion ────────────────────────────────────────
    parent_ids = list({
        c.get("parent_id") or c.get("metadata", {}).get("parent_id", "")
        for c in fused_children
        if c.get("parent_id") or c.get("metadata", {}).get("parent_id")
    })

    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        parent_map = await get_parents_batch(cid, parent_ids, db=db)

    # Build enriched chunks using parent content
    # Deduplicate by parent_id (multiple children → one parent)
    seen_parents: set[str] = set()
    expanded: list[dict]   = []

    for child in fused_children:
        pid = child.get("parent_id") or child.get("metadata", {}).get("parent_id", "")
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

    # ── Step 4: Jina Reranker ─────────────────────────────────────────────────
    try:
        rerank_input_size = max(15, TOP_N_FINAL * 2)
        reranked = await rerank(standalone, expanded[:rerank_input_size])

        # Filter by relevance score to prevent hallucination from irrelevant context
        MIN_RERANK_SCORE = 0.05
        top_reranked = [c for c in reranked if c.get("rerank_score", 0) > MIN_RERANK_SCORE][:TOP_N_FINAL]

    except Exception as e:
        log.warning("Reranker failed", extra={"error": str(e)})
        top_reranked = expanded[:TOP_N_FINAL]

    final = top_reranked

    state["reranked_chunks"] = final
    state["agent_trace"]["retrieval"] = {
        "query_variants":  len(queries),
        "result_lists":    len(all_result_lists),
        "fused_children":  len(fused_children),
        "after_expansion": len(expanded),
        "final":           len(final),
    }

    # ── Cache result ─────────────────────────────────────────────────────────
    await redis.setex(cache_key, CACHE_TTL, json.dumps({"chunks": final}))

    return state
