import logging
import json
from openai import AsyncOpenAI
from app.agents.state import AgentState
from app.config import settings
import asyncio

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

    if state.get("query_type") != "rag":
        state["context_relevant"] = True
        state["agent_trace"]["evaluator"] = "skipped"
        return state

    chunks = state.get("reranked_chunks", [])
    if not chunks:
        state["context_relevant"] = False
        state["agent_trace"]["evaluator"] = "no_chunks"
        return state

    query = state["query"]
    client = _get_client()

    async def _grade_chunk(chunk: dict) -> tuple[dict, bool]:
        user_prompt = f"Question: {query}\n\nDocument:\n{chunk['content']}"
        try:
            resp = await client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
                extra_headers={
                    "HTTP-Referer": settings.FRONTEND_URL,
                    "X-Title": "RAG Evaluator",
                },
            )
            result = json.loads(resp.choices[0].message.content.strip())
            return chunk, result.get("score", "no").lower() == "yes"
        except Exception:
            return chunk, True                                     

                            
    results = await asyncio.gather(*[_grade_chunk(c) for c in chunks])
    
    relevant_chunks = [c for c, is_relevant in results if is_relevant]
    
    if relevant_chunks:
        state["reranked_chunks"] = relevant_chunks                           
        state["context_relevant"] = True
    else:
        state["context_relevant"] = False

    state["agent_trace"]["evaluator"] = {
        "total": len(chunks),
        "kept":  len(relevant_chunks),
        "filtered": len(chunks) - len(relevant_chunks),
    }
    return state