"""LangGraph RAG pipeline."""
from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph
from app.agents.state        import AgentState
from app.agents.router_agent   import router_agent, query_rewriter_node, clarify_node
from app.agents.memory_agent   import memory_load_agent, memory_save_agent
from app.agents.retrieval_agent import retrieval_agent
from app.agents.answer_agent    import answer_agent


from app.agents.evaluator_agent import evaluator_agent
from app.agents.hallucination_agent import hallucination_agent


def _route(state: AgentState) -> str:
    return state["query_type"]   # "rag" | "chitchat" | "summarize" | "clarify"


def check_relevance(state: AgentState) -> str:
    if state.get("query_type") != "rag":
        return "answer"

    if state.get("context_relevant"):
        return "answer"

    # Don't retry if there are no documents in the database
    if not state.get("has_documents"):
        return "answer"

    # If not relevant, and we haven't retried too many times, go back to retrieval
    if state.get("retry_count", 0) < 3:
        state["retry_count"] = state.get("retry_count", 0) + 1
        return "retrieval"
    else:
        # Give up and just answer based on whatever we have
        return "answer"

def check_hallucination(state: AgentState) -> str:
    if state.get("query_type") != "rag":
        return "save"

    if state.get("is_hallucination"):
        # If hallucinated, the hallucination agent already updated the response.
        # Just proceed to save.
        return "save"

    if not state.get("answers_question"):
        # If grounded but doesn't answer, try to retrieve again
        if state.get("retry_count", 0) < 3:
            state["retry_count"] = state.get("retry_count", 0) + 1
            return "retrieval"
        else:
            return "save"

    return "save"


def build_graph() -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("query_rewriter", query_rewriter_node)
    g.add_node("router",    router_agent)
    g.add_node("clarify",   clarify_node)
    g.add_node("memory",    memory_load_agent)
    g.add_node("retrieval", retrieval_agent)
    g.add_node("grade_docs", evaluator_agent)
    g.add_node("answer",    answer_agent)
    g.add_node("grade_gen",  hallucination_agent)
    g.add_node("save",      memory_save_agent)

    g.add_edge(START, "query_rewriter")
    g.add_edge("query_rewriter", "router")

    g.add_conditional_edges("router", _route, {
        "rag":       "memory",
        "summarize": "memory",
        "chitchat":  "answer",
        "clarify":   "clarify",
    })

    g.add_edge("clarify", "save")

    g.add_edge("memory",    "retrieval")
    g.add_edge("retrieval", "grade_docs")

    g.add_conditional_edges("grade_docs", check_relevance, {
        "answer": "answer",
        "retrieval": "retrieval"
    })

    g.add_edge("answer", "grade_gen")

    g.add_conditional_edges("grade_gen", check_hallucination, {
        "answer": "answer",
        "retrieval": "retrieval",
        "save": "save"
    })

    g.add_edge("save",      END)

    return g.compile()


rag_graph = build_graph()
