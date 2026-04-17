"""
Chat router — conversations, messages, documents (nested), SSE streaming.
All document operations are scoped to the parent conversation.
"""
from __future__ import annotations
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.dependencies import get_current_active_user
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import (
    ConversationCreate, ConversationUpdate, ConversationResponse,
    ConversationDetail, DocumentResponse, MessageResponse, ChatRequest,
)
from app.services import document_service
from app.services.quota_service import check_and_increment
from app.agents.graph import rag_graph
from app.agents.state import AgentState
from app.middleware.rate_limiter import check_rate_limit
from app.config import settings

router = APIRouter(prefix="/chat", tags=["chat"])
log    = logging.getLogger(__name__)


# ── Guard ─────────────────────────────────────────────────────────────────────
async def _get_conversation(
    conversation_id: UUID,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Conversation:
    conv = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    if not conv:
        raise HTTPException(404, detail="Conversation not found.")
    return conv


# ── Conversations CRUD ────────────────────────────────────────────────────────
@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )
    return result.scalars().all()


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    conv = Conversation(user_id=current_user.id, title=body.title, document_count=0)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    docs = await document_service.list_documents(db, conversation.id)
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
    return ConversationDetail(
        **ConversationResponse.model_validate(conversation).model_dump(),
        documents=[DocumentResponse.model_validate(d) for d in docs],
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    body: ConversationUpdate,
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    conversation.title = body.title
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    from app.retrieval.vector_retriever import delete_conversation_collection
    from app.retrieval.bm25_retriever import bm25_retriever

    conv_id = str(conversation.id)
    await db.delete(conversation)
    await db.commit()
    await delete_conversation_collection(conv_id)
    bm25_retriever.invalidate(conv_id)


# ── Messages ──────────────────────────────────────────────────────────────────
@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def list_messages(
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()


# ── Chat — SSE Streaming ──────────────────────────────────────────────────────
@router.post("/conversations/{conversation_id}/message")
async def send_message(
    body: ChatRequest,
    conversation: Conversation = Depends(_get_conversation),
    current_user=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Rate limit + quota
    await check_rate_limit(str(current_user.id), window_seconds=60, limit=settings.RATE_LIMIT_PER_MINUTE)
    await check_and_increment(current_user.id, db)

    state = AgentState(
        user_id=str(current_user.id),
        conversation_id=str(conversation.id),
        query=body.query,
        query_type="",
        history=[],
        bm25_results=[],
        vector_results=[],
        fused_chunks=[],
        reranked_chunks=[],
        response="",
        token_count=0,
        agent_trace={},
        error=None,
        should_stream=True,
        has_documents=conversation.document_count > 0,
        document_count=conversation.document_count,
    )

    async def event_stream():
        # Buffer to accumulate streamed text
        buffer: list[str] = []

        try:
            async for event in rag_graph.astream(state):
                node = list(event.keys())[0]
                data = event[node]

                if node == "answer":
                    # Stream each word of the response as it builds
                    current_response = data.get("response", "")
                    already_sent     = len("".join(buffer))
                    new_chunk        = current_response[already_sent:]
                    if new_chunk:
                        buffer.append(new_chunk)
                        yield f"data: {json.dumps({'type': 'chunk', 'content': new_chunk})}\n\n"

                elif node == "save":
                    sources = [
                        {
                            "content":  c.get("content", "")[:200],
                            "filename": c.get("metadata", {}).get("filename", ""),
                            "score":    round(c.get("rerank_score", 0), 4),
                        }
                        for c in data.get("reranked_chunks", [])
                    ]
                    yield f"data: {json.dumps({'type': 'done', 'sources': sources})}\n\n"

        except Exception as e:
            log.error("Stream error", extra={"error": str(e)})
            yield f"data: {json.dumps({'type': 'error', 'message': 'An error occurred.'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Documents (nested) ────────────────────────────────────────────────────────
@router.get(
    "/conversations/{conversation_id}/documents",
    response_model=list[DocumentResponse],
)
async def list_documents(
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.list_documents(db, conversation.id)


@router.post(
    "/conversations/{conversation_id}/documents",
    response_model=DocumentResponse,
    status_code=202,
)
async def upload_document(
    file: UploadFile = File(...),
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.upload_document(db, conversation, file)


@router.get(
    "/conversations/{conversation_id}/documents/{document_id}",
    response_model=DocumentResponse,
)
async def get_document_status(
    document_id: UUID,
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.get_document(db, document_id, conversation.id)


@router.delete(
    "/conversations/{conversation_id}/documents/{document_id}",
    status_code=204,
)
async def delete_document(
    document_id: UUID,
    conversation: Conversation = Depends(_get_conversation),
    db: AsyncSession = Depends(get_db),
):
    doc = await document_service.get_document(db, document_id, conversation.id)
    await document_service.delete_document(db, doc, conversation)
