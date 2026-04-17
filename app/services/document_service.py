"""Document service — scoped to conversation."""
from __future__ import annotations
import logging, uuid
from uuid import UUID
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.document import Document
from app.models.conversation import Conversation

log = logging.getLogger(__name__)

ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
MAX_SIZE = 50 * 1024 * 1024   # 50 MB
MAX_DOCS = 20


async def upload_document(db: AsyncSession, conversation: Conversation, file: UploadFile) -> Document:
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, detail="Only PDF, DOCX, and TXT files are supported.")
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, detail="File exceeds 50 MB limit.")
    if conversation.document_count >= MAX_DOCS:
        raise HTTPException(400, detail=f"Maximum {MAX_DOCS} documents per conversation.")

    doc_id    = str(uuid.uuid4())
    file_path = f"{conversation.id}/{doc_id}_{file.filename}"

    from app import storage
    await storage.put_object(file_path, content, file.content_type)

    doc = Document(
        id=doc_id,
        conversation_id=conversation.id,
        filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type=file.content_type,
        status="pending",
    )
    db.add(doc)
    conversation.document_count += 1
    await db.commit()
    await db.refresh(doc)

    from app.tasks.ingestion_tasks import process_document
    process_document.delay(str(doc.id))

    log.info("Document uploaded", extra={"doc_id": doc_id, "conversation_id": str(conversation.id)})
    return doc


async def list_documents(db: AsyncSession, conversation_id: UUID) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.conversation_id == conversation_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document(db: AsyncSession, document_id: UUID, conversation_id: UUID) -> Document:
    doc = await db.scalar(
        select(Document).where(and_(
            Document.id == document_id,
            Document.conversation_id == conversation_id,
        ))
    )
    if not doc:
        raise HTTPException(404, detail="Document not found.")
    return doc


async def delete_document(db: AsyncSession, document: Document, conversation: Conversation) -> None:
    from app import storage
    from app.retrieval.vector_retriever import delete_document_chunks
    from app.retrieval.bm25_retriever import bm25_retriever

    # 1. MinIO
    try:
        await storage.remove_object(document.file_path)
    except Exception as e:
        log.warning("MinIO delete failed", extra={"error": str(e)})

    # 2. ChromaDB
    await delete_document_chunks(str(conversation.id), str(document.id))

    # 3. DB (CASCADE removes chunks)
    await db.delete(document)
    conversation.document_count = max(0, conversation.document_count - 1)
    await db.commit()

    # 4. Rebuild BM25
    await bm25_retriever.rebuild_async(db, str(conversation.id))
    log.info("Document deleted", extra={"doc_id": str(document.id)})
