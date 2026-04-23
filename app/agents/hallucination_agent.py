import logging
import json
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

COMBINED_SYSTEM = """You are an expert evaluator assessing an LLM generation.
You must output a JSON object with exactly three keys:
1. "is_grounded": boolean (true if the answer is grounded in and supported by the provided facts. False if it contains made-up information or contradicts the facts).
2. "answers_question": boolean (true if the answer actually resolves the user's question, false if it evades or fails to answer it).
3. "fallback_message": string (If either is_grounded is false OR answers_question is false, output the phrase "Tôi không tìm thấy thông tin về vấn đề này trong tài liệu.". If both are true, this can be empty).

If the answer is essentially "I don't know" or "There is no information", then is_grounded=true but answers_question=false.
Provide only the JSON object. No markdown, no explanations."""

async def hallucination_agent(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})

                                                  
    if state.get("query_type") != "rag":
        state["is_hallucination"] = False
        state["answers_question"] = True
        state["agent_trace"]["hallucination"] = "skipped"
        return state

    chunks = state.get("reranked_chunks", [])
    response = state.get("response", "")

    if not response:
        state["is_hallucination"] = False
        state["answers_question"] = False
        state["agent_trace"]["hallucination"] = "no_response"
        return state

    retry_count = state.get("retry_count", 0)

    if not chunks:
                                                                                                                                   
        is_grounded = "don't know" in response.lower() or "cannot answer" in response.lower()
        state["is_hallucination"] = not is_grounded
        state["answers_question"] = False
        state["agent_trace"]["hallucination"] = "no_chunks_check"

        will_save = not is_grounded or (not state["answers_question"] and retry_count >= 3)
        if will_save:
            state["response"] = "Tôi không tìm thấy thông tin về vấn đề này trong tài liệu."
        return state

                   
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"[Source {i}]\n{chunk['content']}")
    context = "\n\n---\n\n".join(context_parts)

    try:
        client = _get_client()

        eval_prompt = f"User question: {state['query']}\n\nSet of facts:\n{context}\n\nLLM generation to evaluate:\n{response}"

        eval_resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": COMBINED_SYSTEM},
                {"role": "user", "content": eval_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            extra_headers={
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "RAG Evaluator",
            },
        )

        result_text = eval_resp.choices[0].message.content.strip()
        result_json = json.loads(result_text)

        is_grounded = result_json.get("is_grounded", True)
        answers_question = result_json.get("answers_question", True)

        state["is_hallucination"] = not is_grounded
        state["answers_question"] = answers_question

        will_save = not is_grounded or (not answers_question and retry_count >= 3)
        if will_save and (not is_grounded or not answers_question):
            fallback = result_json.get("fallback_message")
            if fallback:
                state["response"] = fallback
            else:
                state["response"] = "Tôi không tìm thấy thông tin về vấn đề này trong tài liệu."

        state["agent_trace"]["hallucination"] = {
            "grounded": is_grounded,
            "answers": state["answers_question"]
        }

    except Exception as e:
        log.error("Hallucination/Answer LLM error", extra={"error": str(e)})
                              
        state["is_hallucination"] = False
        state["answers_question"] = True
        state["agent_trace"]["hallucination"] = f"error: {str(e)}"

    return state
