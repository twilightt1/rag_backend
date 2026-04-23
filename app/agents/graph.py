from langgraph.graph import StateGraph, END, START
from langgraph.graph.state import CompiledStateGraph
from app.agents.state        import AgentState
from app.agents.router_agent   import router_agent
from app.agents.memory_agent   import memory_load_agent, memory_save_agent
from app.agents.retrieval_agent import retrieval_agent
from app.agents.answer_agent    import answer_agent
from app.agents.hallucination_agent import hallucination_agent


def _route(state: AgentState) -> str:
    return state["query_type"]                                     


def build_graph() -> CompiledStateGraph:
    g = StateGraph(AgentState)

    g.add_node("router",    router_agent)
    g.add_node("memory",    memory_load_agent)
    g.add_node("retrieval", retrieval_agent)
    g.add_node("answer",    answer_agent)
    g.add_node("grade_gen",  hallucination_agent)
    g.add_node("save",      memory_save_agent)

    g.add_edge(START, "router")

    g.add_conditional_edges("router", _route, {
        "rag":       "memory",
        "summarize": "memory",
        "chitchat":  "answer",
    })

    g.add_edge("memory",    "retrieval")
    g.add_edge("retrieval", "answer")
    g.add_edge("answer", "grade_gen")
    g.add_edge("grade_gen", "save")
    g.add_edge("save",      END)

    return g.compile()


rag_graph = build_graph()
