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


                                                                                

CONV_SYSTEM = """You are a query reformulation assistant.
Given a conversation history and a follow-up question, rewrite the follow-up
into a fully self-contained question that can be understood without the history.

Rules:
- If the question is already standalone, return it unchanged.
- Resolve pronouns, ellipsis, and references to prior messages.
- Return ONLY the rewritten question. No explanation, no quotes."""


async def conversation_rewrite(query: str, history: list[dict]) -> str:
    if not history:
        return query

                                                
    recent = history[-6:]
    hist_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent
    )
    user_prompt = f"Conversation history:\n{hist_text}\n\nFollow-up question: {query}"
    result = await _call(CONV_SYSTEM, user_prompt, max_tokens=200)
    return result or query


                                                                                

REWRITE_SYSTEM = """You are a query rewriting assistant.
Rewrite the given search query to improve retrieval accuracy.
Use different vocabulary and phrasing while preserving the exact meaning.
Return ONLY the rewritten query. No explanation."""


async def query_rewrite(query: str) -> str:
    result = await _call(REWRITE_SYSTEM, query, max_tokens=150)
    return result or query


                                                                                

MULTI_QUERY_SYSTEM = """You are a query expansion assistant.
Generate {n} distinct search queries that approach the user's question from
different angles or use different terminology. The goal is to improve document
retrieval coverage.

Output a JSON array of strings and nothing else. Example:
["query one", "query two", "query three"]"""


async def multi_query(query: str, n: int = 3) -> list[str]:
    system = MULTI_QUERY_SYSTEM.format(n=n)
    raw    = await _call(system, query, max_tokens=300)

    variants: list[str] = []
    try:
                                 
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            variants = [str(v).strip() for v in parsed if str(v).strip()]
    except (json.JSONDecodeError, ValueError):
                                      
        for line in raw.splitlines():
            line = line.strip().strip('"').strip("'").strip("-").strip()
            if line and len(line) > 5:
                variants.append(line)

                                                    
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


                                                                                

HYDE_SYSTEM = """You are a knowledgeable assistant.
Write a short, factual passage (2-4 sentences) that would directly answer
the following question. Write as if it were an excerpt from a reference document.
Do NOT say "I don't know" — produce a plausible answer based on general knowledge.
Return ONLY the passage text."""


async def hyde(query: str) -> str:
    result = await _call(HYDE_SYSTEM, query, max_tokens=200)
    return result or query


                                                                                

async def process_query(
    query: str,
    history: list[dict],
    use_rewrite:     bool = True,
    use_multi_query: bool = True,
    use_hyde:        bool = True,
    n_variants:      int  = 3,
) -> "QueryBundle":
                                                                       
    standalone = await conversation_rewrite(query, history)

                                              
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


                                                                                

class QueryBundle:

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
        self.variants   = variants                                          
        self.hyde_text  = hyde_text

    def all_queries(self) -> list[str]:
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
