from app.agents.state import AgentState
import re

CHITCHAT = [r"\bxin chào\b", r"\bhello\b", r"\bhi\b", r"\bhey\b", r"\bbạn là ai\b", r"\bwho are you\b", r"\bcảm ơn\b", r"\bthank\b", r"\bthanks\b", r"\bwhat can you do\b"]
CHITCHAT_PATTERN = re.compile("|".join(CHITCHAT), re.IGNORECASE)

async def router_agent(state: AgentState) -> AgentState:
    q = state["query"].lower().strip()
    state.setdefault("agent_trace", {})
    if not state.get("has_documents") or CHITCHAT_PATTERN.search(q):
        state["query_type"] = "chitchat"
    else:
        state["query_type"] = "rag"
    state["agent_trace"]["router"] = state["query_type"]
    return state
