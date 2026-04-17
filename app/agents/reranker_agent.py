import logging
from app.agents.state import AgentState
from app.retrieval.reranker import rerank

log = logging.getLogger(__name__)

async def reranker_agent(state: AgentState) -> AgentState:
    chunks = state.get("fused_chunks", [])
    state.setdefault("agent_trace", {})
    if not chunks:
        state["reranked_chunks"] = []
        state["agent_trace"]["reranker"] = "skipped"
        return state
    try:
        reranked = await rerank(state["query"], chunks)
        state["reranked_chunks"] = reranked
        state["agent_trace"]["reranker"] = [round(c.get("rerank_score", 0), 4) for c in reranked]
    except Exception as e:
        log.warning("Reranker failed, using fused order", extra={"error": str(e)})
        state["reranked_chunks"] = chunks[:5]
        state["agent_trace"]["reranker"] = f"fallback:{e}"
    return state
