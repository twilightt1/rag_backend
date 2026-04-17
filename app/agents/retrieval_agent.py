import asyncio, hashlib, json, logging
from app.agents.state import AgentState
from app.retrieval.bm25_retriever import bm25_retriever
from app.retrieval.vector_retriever import search as vector_search
from app.retrieval.hybrid_retriever import reciprocal_rank_fusion
from app.redis_client import get_redis

log = logging.getLogger(__name__)

async def retrieval_agent(state: AgentState) -> AgentState:
    cid = state["conversation_id"]
    state.setdefault("agent_trace", {})
    if not state.get("has_documents"):
        state.update({"fused_chunks": [], "bm25_results": [], "vector_results": []})
        state["agent_trace"]["retrieval"] = "no_documents"
        return state

    cache_key = f"rag:query:conv:{cid}:{hashlib.md5(state['query'].encode()).hexdigest()}"
    redis = await get_redis()
    cached = await redis.get(cache_key)
    if cached:
        state["fused_chunks"] = json.loads(cached)
        state["agent_trace"]["retrieval"] = "cache_hit"
        return state

    bm25_r, vec_r = await asyncio.gather(
        bm25_retriever.search(state["query"], 20, cid),
        vector_search(state["query"], 20, cid),
    )
    fused = reciprocal_rank_fusion([bm25_r, vec_r])[:15]
    state.update({"bm25_results": bm25_r, "vector_results": vec_r, "fused_chunks": fused})
    await redis.setex(cache_key, 300, json.dumps(fused))
    state["agent_trace"]["retrieval"] = {"bm25": len(bm25_r), "vector": len(vec_r)}
    return state
