from typing import TypedDict, Any

class AgentState(TypedDict, total=False):
    user_id:         str
    conversation_id: str
    query:           str
    query_type:      str
    history:         list[dict]
    bm25_results:    list[dict]
    vector_results:  list[dict]
    fused_chunks:    list[dict]
    reranked_chunks: list[dict]
    response:        str
    token_count:     int
    agent_trace:     dict
    error:           str | None
    should_stream:   bool
    has_documents:   bool
    document_count:  int
    _stream_callback: Any
