"""Agent state — extended for Advanced RAG pipeline."""
from typing import TypedDict


class AgentState(TypedDict):
    # Input
    user_id:         str
    conversation_id: str
    query:           str
    rewritten_query: str          # output of query_rewriter_node

    # Router
    query_type:      str          # "rag" | "chitchat" | "summarize" | "clarify"
    router_confidence: float      # confidence score from router
    router_reasoning:  str        # reasoning string for debug/tracing
    clarify_reasoning: str        # passed to clarify_node prompt

    # Memory
    history:         list[dict]   # [{"role": "user"|"assistant", "content": "..."}]

    # Retrieval (child chunks — raw from BM25 + vector)
    bm25_results:    list[dict]
    vector_results:  list[dict]
    fused_chunks:    list[dict]   # RRF-merged children

    # After parent expansion + compression + reranking
    reranked_chunks: list[dict]   # final parent-level chunks sent to LLM

    # Answer
    response:        str
    token_count:     int
    agent_trace:     dict         # full audit trail of the pipeline

    # Control
    error:           str | None
    should_stream:   bool
    has_documents:   bool         # False → skip retrieval entirely
    document_count:  int

    # Multi-Agent Evaluation state
    context_relevant: bool
    is_hallucination: bool
    answers_question: bool
    retry_count:      int
