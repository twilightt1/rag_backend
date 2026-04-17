"""Chat endpoint tests (minimal)."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_conversations_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/chat/conversations")
    assert resp.status_code == 403
