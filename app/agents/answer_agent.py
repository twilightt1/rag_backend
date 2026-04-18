"""Answer agent — streams response from OpenRouter LLM."""
import logging
from openai import AsyncOpenAI
from app.agents.state import AgentState
from app.config import settings

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
        )
    return _client


SYSTEM_PROMPT = """You are an intelligent AI assistant. Answer questions based on the provided context.
If the user asks for a summary, synthesize a comprehensive summary of the main topics and themes covered in the provided excerpts. IT IS CRITICAL THAT YOU DO NOT REFUSE TO SUMMARIZE. Even if the excerpts seem completely disjointed, unrelated, or from multiple sources, you MUST provide a summary of the topics discussed. Do not state that there is no single document, and do not ask the user for a complete document. Just summarize what you are given.
If the context does not contain enough information to answer a specific factual question, say so clearly.
Be concise, accurate, and helpful. Respond in the same language as the user's question."""


async def answer_agent(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})

    # Build context from reranked chunks
    if state.get("query_type") == "summarize" and state.get("reranked_chunks"):
        context_parts = []
        for i, chunk in enumerate(state["reranked_chunks"], 1):
            fname = chunk.get("metadata", {}).get("filename", "unknown")
            context_parts.append(f"=== DOCUMENT: {fname} ===\n{chunk['content']}\n=== END OF {fname} ===")
        context = "\n\n".join(context_parts)
        system  = f"You are an expert analyst. The user has provided the full text of one or more documents below. Please provide a comprehensive, well-structured summary of these documents. DO NOT complain about the text being disjointed, because it is the full document text reconstructed. Just summarize it.\n\n{context}"
    elif state.get("query_type") == "rag" and state.get("reranked_chunks"):
        context_parts = []
        for i, chunk in enumerate(state["reranked_chunks"], 1):
            fname = chunk.get("metadata", {}).get("filename", "unknown")
            context_parts.append(f"[Source {i} - {fname}]\n{chunk['content']}")
        context = "\n\n---\n\n".join(context_parts)
        system  = f"{SYSTEM_PROMPT}\n\nContext:\n{context}"
    else:
        system = SYSTEM_PROMPT

    messages = [{"role": "system", "content": system}]
    for h in state.get("history", []):
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": state["query"]})

    full_response = ""
    token_count   = 0

    try:
        stream = await _get_client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            stream=True,
            extra_headers={
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "RAG System",
            },
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            full_response += delta
            # Yield chunk for SSE — stored in state for non-streaming callers
            cb = state.get("_stream_callback")
            if cb:
                await cb(delta)

            if chunk.usage:
                token_count = chunk.usage.total_tokens

    except Exception as e:
        log.error("LLM error", extra={"error": str(e)})
        full_response = f"Sorry, I encountered an error while generating a response. Error: {str(e)}"

    state["response"]    = full_response
    state["token_count"] = token_count
    state["agent_trace"]["answer"] = {
        "model": settings.LLM_MODEL,
        "tokens": token_count,
        "context_chunks": len(state.get("reranked_chunks", [])),
    }
    return state
