"""Evaluator agent — grades retrieved documents against the query."""
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

SYSTEM_PROMPT = """You are a grader assessing relevance of a retrieved document to a user question.
If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant.
It does not need to be a stringent test. The goal is to filter out erroneous retrievals.

Provide your output as a JSON object with a single key "score" and value "yes" or "no". No other text."""

async def evaluator_agent(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})
    state.setdefault("retry_count", 0)

    # If not a rag query, skip evaluation
    if state.get("query_type") != "rag":
        state["context_relevant"] = True
        state["agent_trace"]["evaluator"] = "skipped"
        return state

    chunks = state.get("reranked_chunks", [])
    if not chunks:
        # If no chunks were found but it's a RAG query, context is irrelevant
        state["context_relevant"] = False
        state["agent_trace"]["evaluator"] = "no_chunks"
        return state

    # Combine all chunks for grading
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        fname = chunk.get("metadata", {}).get("filename", "unknown")
        context_parts.append(f"[Source {i} - {fname}]\n{chunk['content']}")
    context = "\n\n---\n\n".join(context_parts)

    user_prompt = f"Retrieved document:\n\n{context}\n\nUser question: {state['query']}"

    try:
        resp = await _get_client().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            extra_headers={
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "RAG Evaluator",
            },
        )
        result_text = resp.choices[0].message.content.strip()
        result_json = json.loads(result_text)
        score = result_json.get("score", "no").lower()

        is_relevant = (score == "yes")
        state["context_relevant"] = is_relevant
        state["agent_trace"]["evaluator"] = score

    except Exception as e:
        log.error("Evaluator LLM error", extra={"error": str(e)})
        # On error, default to True so we don't block the pipeline unnecessarily
        state["context_relevant"] = True
        state["agent_trace"]["evaluator"] = f"error: {str(e)}"

    return state
