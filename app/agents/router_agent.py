from app.agents.state import AgentState

CHITCHAT = ["xin chào","hello","hi","hey","bạn là ai","who are you","cảm ơn","thank","thanks","what can you do"]

async def router_agent(state: AgentState) -> AgentState:
    q = state["query"].lower().strip()
    state.setdefault("agent_trace", {})
    if not state.get("has_documents") or any(p in q for p in CHITCHAT):
        state["query_type"] = "chitchat"
    else:
        state["query_type"] = "rag"
    state["agent_trace"]["router"] = state["query_type"]
    return state
