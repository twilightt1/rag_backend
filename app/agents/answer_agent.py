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
If the context does not contain enough information, say so clearly.
Be concise, accurate, and helpful. Respond in the same language as the user's question."""


async def answer_agent(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})

    # Build context from reranked chunks
    if state.get("query_type") == "rag" and state.get("reranked_chunks"):
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
            if hasattr(state, "_stream_callback") and state._stream_callback:
                await state._stream_callback(delta)

            if chunk.usage:
                token_count = chunk.usage.total_tokens

    except Exception as e:
        log.error("LLM error", extra={"error": str(e)})
        full_response = "Sorry, I encountered an error while generating a response. Please try again."

    state["response"]    = full_response
    state["token_count"] = token_count
    state["agent_trace"]["answer"] = {
        "model": settings.LLM_MODEL,
        "tokens": token_count,
        "context_chunks": len(state.get("reranked_chunks", [])),
    }
    return state
