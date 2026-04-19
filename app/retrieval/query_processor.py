"""
Query processor — runs before retrieval.

Four transformations (all use OpenRouter LLM):

1. conversation_rewrite  — turn conversational follow-up into standalone query
   "What about its memory?" + history → "How does Transformer handle memory?"

2. query_rewrite         — paraphrase for lexical diversity
   → one alternative phrasing of the same question

3. multi_query           — generate N semantically varied queries
   → retrieves wider coverage, merged via RRF

4. hyde                  — Hypothetical Document Embeddings
   → generate a fake answer, embed it, use for vector search
   (better signal than embedding the question alone)

The caller decides which to use. retrieval_agent uses all four in parallel.
"""
from __future__ import annotations
import asyncio
import json
import logging
from openai import AsyncOpenAI
from app.config import settings

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _llm() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
        )
    return _client


async def _call(system: str, user: str, max_tokens: int = 512) -> str:
    """Single LLM call — returns text content."""
    try:
        resp = await _llm().chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
            extra_headers={
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "RAG Query Processor",
            },
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning("LLM call failed", extra={"error": str(e)})
        return ""


# ── 1. Conversation-aware rewrite ─────────────────────────────────────────────

CONV_SYSTEM = """You are a query reformulation assistant.
Given a conversation history and a follow-up question, rewrite the follow-up
into a fully self-contained question that can be understood without the history.

Rules:
- If the question is already standalone, return it unchanged.
- Resolve pronouns, ellipsis, and references to prior messages.
- Return ONLY the rewritten question. No explanation, no quotes."""


async def conversation_rewrite(query: str, history: list[dict]) -> str:
    """
    Rewrite follow-up query into standalone query using conversation history.
    history: [{"role": "user"|"assistant", "content": "..."}]
    """
    if not history:
        return query

    # Limit to last 6 turns to keep prompt small
    recent = history[-6:]
    hist_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent
    )
    user_prompt = f"Conversation history:\n{hist_text}\n\nFollow-up question: {query}"
    result = await _call(CONV_SYSTEM, user_prompt, max_tokens=200)
    return result or query


# ── 2. Query rewrite (paraphrase) ─────────────────────────────────────────────

REWRITE_SYSTEM = """You are a query rewriting assistant.
Rewrite the given search query to improve retrieval accuracy.
Use different vocabulary and phrasing while preserving the exact meaning.
Return ONLY the rewritten query. No explanation."""


async def query_rewrite(query: str) -> str:
    """Paraphrase query for lexical diversity."""
    result = await _call(REWRITE_SYSTEM, query, max_tokens=150)
    return result or query


# ── 3. Multi-query generation ─────────────────────────────────────────────────

MULTI_QUERY_SYSTEM = """You are a query expansion assistant.
Generate {n} distinct search queries that approach the user's question from
different angles or use different terminology. The goal is to improve document
retrieval coverage.

Output a JSON array of strings and nothing else. Example:
["query one", "query two", "query three"]"""


async def multi_query(query: str, n: int = 3) -> list[str]:
    """
    Generate N query variants for broader retrieval coverage.
    Returns original query + variants (deduped).
    """
    system = MULTI_QUERY_SYSTEM.format(n=n)
    raw    = await _call(system, query, max_tokens=300)

    variants: list[str] = []
    try:
        # Try to parse JSON array
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            variants = [str(v).strip() for v in parsed if str(v).strip()]
    except (json.JSONDecodeError, ValueError):
        # Fallback: parse line by line
        for line in raw.splitlines():
            line = line.strip().strip('"').strip("'").strip("-").strip()
            if line and len(line) > 5:
                variants.append(line)

    # Deduplicate and limit, always include original
    all_queries = [query] + variants
    seen        = set()
    result      = []
    for q in all_queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            result.append(q)
        if len(result) >= n + 1:
            break

    return result or [query]


# ── 4. HyDE — Hypothetical Document Embedding ─────────────────────────────────

HYDE_SYSTEM = """You are a knowledgeable assistant.
Write a short, factual passage (2-4 sentences) that would directly answer
the following question. Write as if it were an excerpt from a reference document.
Do NOT say "I don't know" — produce a plausible answer based on general knowledge.
Return ONLY the passage text."""


async def hyde(query: str) -> str:
    """
    Generate a hypothetical document passage to embed for retrieval.
    The embedding of this passage is often closer to relevant real chunks
    than embedding the question alone.
    """
    result = await _call(HYDE_SYSTEM, query, max_tokens=200)
    return result or query


# ── Combined: run all transforms in parallel ──────────────────────────────────

async def process_query(
    query: str,
    history: list[dict],
    use_rewrite:     bool = True,
    use_multi_query: bool = True,
    use_hyde:        bool = True,
    n_variants:      int  = 3,
) -> "QueryBundle":
    """
    Run all query transforms in parallel.
    Returns a QueryBundle with all variants ready for retrieval.
    """
    # Step 1: Conversation rewrite (sequential — others depend on this)
    standalone = await conversation_rewrite(query, history)

    # Step 2: Remaining transforms in parallel
    tasks = {}
    if use_rewrite:
        tasks["rewrite"]     = query_rewrite(standalone)
    if use_multi_query:
        tasks["multi"]       = multi_query(standalone, n=n_variants)
    if use_hyde:
        tasks["hyde"]        = hyde(standalone)

    results = {}
    if tasks:
        done = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, res in zip(tasks.keys(), done):
            if isinstance(res, Exception):
                log.warning(f"Query transform '{key}' failed", extra={"error": str(res)})
                results[key] = None
            else:
                results[key] = res

    rewritten   = results.get("rewrite") or standalone
    variants    = results.get("multi")   or [standalone]
    hyde_text   = results.get("hyde")    or standalone

    log.info(
        "Query processed",
        extra={
            "original":   query[:60],
            "standalone": standalone[:60],
            "variants":   len(variants),
            "hyde":       bool(hyde_text != standalone),
        },
    )
    return QueryBundle(
        original=query,
        standalone=standalone,
        rewritten=rewritten,
        variants=variants,
        hyde_text=hyde_text,
    )


# ── QueryBundle ───────────────────────────────────────────────────────────────

class QueryBundle:
    """Container for all query variants produced by process_query()."""

    def __init__(
        self,
        original:   str,
        standalone: str,
        rewritten:  str,
        variants:   list[str],
        hyde_text:  str,
    ):
        self.original   = original
        self.standalone = standalone
        self.rewritten  = rewritten
        self.variants   = variants    # includes standalone as first element
        self.hyde_text  = hyde_text

    def all_queries(self) -> list[str]:
        """All unique query strings to use for retrieval."""
        all_q = [self.standalone, self.rewritten] + self.variants
        seen, result = set(), []
        for q in all_q:
            if q and q.lower() not in seen:
                seen.add(q.lower())
                result.append(q)
        return result

    def to_dict(self) -> dict:
        return {
            "original":   self.original,
            "standalone": self.standalone,
            "rewritten":  self.rewritten,
            "variants":   self.variants,
            "hyde_text":  self.hyde_text,
        }
