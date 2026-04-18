import asyncio, hashlib, json, logging
from app.agents.state import AgentState
from app.retrieval.bm25_retriever import bm25_retriever
from app.retrieval.vector_retriever import search as vector_search
from app.retrieval.hybrid_retriever import reciprocal_rank_fusion
from app.redis_client import get_redis
from app.database import AsyncSessionLocal
from sqlalchemy import select
from app.models.document_chunk import DocumentChunk
from app.models.document import Document

log = logging.getLogger(__name__)

async def retrieval_agent(state: AgentState) -> AgentState:
    cid = state["conversation_id"]
    state.setdefault("agent_trace", {})
    if not state.get("has_documents"):
        state.update({"fused_chunks": [], "bm25_results": [], "vector_results": []})
        state["agent_trace"]["retrieval"] = "no_documents"
        return state

    if state.get("query_type") == "summarize":
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(DocumentChunk, Document.filename)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(Document.conversation_id == cid, Document.status == "ready")
                .order_by(Document.id, DocumentChunk.chunk_index)
            )
            rows = result.all()

            # Group chunks by document to reconstruct the full coherent text
            docs_content = {}
            for chunk, filename in rows:
                if filename not in docs_content:
                    docs_content[filename] = []
                docs_content[filename].append(chunk.content)

            chunks = []
            for filename, contents in docs_content.items():
                full_text = "\n".join(contents)
                # Cap at ~300k chars per doc to prevent extreme context overflow,
                # but enough for the latest models to read large documents.
                MAX_CHARS_PER_DOC = 300000
                if len(full_text) > MAX_CHARS_PER_DOC:
                    full_text = full_text[:MAX_CHARS_PER_DOC] + "\n... [TRUNCATED]"

                chunks.append({
                    "id": filename,
                    "content": full_text,
                    "metadata": {"filename": filename},
                    "score": 1.0
                })

            state.update({"bm25_results": [], "vector_results": [], "fused_chunks": chunks})
            state["agent_trace"]["retrieval"] = {"full_documents": len(chunks)}
            return state

    cache_key = f"rag:query:conv:{cid}:{hashlib.md5(state['query'].encode()).hexdigest()}"
    redis = await get_redis()
    cached = await redis.get(cache_key)
    if cached:
        state["fused_chunks"] = json.loads(cached)
        state["agent_trace"]["retrieval"] = "cache_hit"
        return state

    bm25_r, vec_r = await asyncio.gather(
        bm25_retriever.search(state["query"], 20, cid),
        vector_search(state["query"], 20, cid),
    )
    fused = reciprocal_rank_fusion([bm25_r, vec_r])[:15]
    state.update({"bm25_results": bm25_r, "vector_results": vec_r, "fused_chunks": fused})
    await redis.setex(cache_key, 300, json.dumps(fused))
    state["agent_trace"]["retrieval"] = {"bm25": len(bm25_r), "vector": len(vec_r)}
    return state
