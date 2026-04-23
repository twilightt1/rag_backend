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


SYSTEM_PROMPT = """You are a precise RAG assistant. Your ONLY job is to answer questions using the provided context.

STRICT RULES:
1. Every factual claim MUST be supported by a [Source N] citation from the context below.
2. If the context does not contain enough information, respond ONLY with: "Tôi không tìm thấy thông tin về vấn đề này trong tài liệu." but translate it to the language of the user's question. For example, if the question is in Vietnamese, respond with the Vietnamese sentence. If it's in English, respond with "I couldn't find information about this issue in the documents."
3. Do NOT use your general knowledge to fill gaps — if it's not in the context, it doesn't exist.
4. Do NOT speculate, extrapolate, or infer beyond what is explicitly stated.
5. Respond in the EXACT SAME LANGUAGE as the user's question.

Format example:
"Thời hạn bảo hành là 12 tháng [Source 1]. Điều kiện áp dụng bao gồm... [Source 2]."
"""


async def answer_agent(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})

                                        
    if state.get("query_type") == "summarize" and state.get("reranked_chunks"):
        context_parts = []
        for i, chunk in enumerate(state["reranked_chunks"], 1):
            fname = chunk.get("metadata", {}).get("filename", "unknown")
            context_parts.append(f"=== DOCUMENT: {fname} ===\n{chunk['content']}\n=== END OF {fname} ===")
        context = "\n\n".join(context_parts)
        system  = f"You are an expert analyst. The user has provided the full text of one or more documents below. Please provide a comprehensive, well-structured summary of these documents. DO NOT complain about the text being disjointed, because it is the full document text reconstructed. Just summarize it.\nIMPORTANT: You MUST respond in the EXACT SAME LANGUAGE as the user's request.\n\n{context}"
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
