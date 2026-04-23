import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.retrieval.embedder import embed_texts, embed_query, embed_texts_sync

@pytest.mark.asyncio
@patch("app.retrieval.embedder.async_client")
async def test_embed_texts_async(mock_client):
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3]),
        MagicMock(embedding=[0.4, 0.5, 0.6]),
    ]
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)

    texts = ["hello", "world"]
    embeddings = await embed_texts(texts)

    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3]
    assert embeddings[1] == [0.4, 0.5, 0.6]

@pytest.mark.asyncio
@patch("app.retrieval.embedder.async_client")
async def test_embed_query_async(mock_client):
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.7, 0.8, 0.9]),
    ]
    mock_client.embeddings.create = AsyncMock(return_value=mock_response)

    query = "search term"
    embedding = await embed_query(query)

    assert isinstance(embedding, list)
    assert embedding == [0.7, 0.8, 0.9]

@patch("app.retrieval.embedder.sync_client")
def test_embed_texts_sync(mock_client):
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1, 0.2, 0.3]),
    ]
    mock_client.embeddings.create = MagicMock(return_value=mock_response)

    texts = ["hello"]
    embeddings = embed_texts_sync(texts)

    assert len(embeddings) == 1
    assert embeddings[0] == [0.1, 0.2, 0.3]

@pytest.mark.asyncio
@patch("app.retrieval.embedder.async_client")
async def test_embed_empty(mock_client):
    embeddings = await embed_texts([])
    assert embeddings == []
    mock_client.embeddings.create.assert_not_called()

    sync_embeddings = embed_texts_sync([])
    assert sync_embeddings == []
