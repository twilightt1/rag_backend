"""Auth endpoint tests."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "SecurePass123",
    })
    assert resp.status_code == 201
    assert "message" in resp.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "SecurePass123"}
    await client.post("/api/v1/auth/register", json=payload)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_login_unverified(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "unverified@example.com",
        "password": "SecurePass123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "unverified@example.com",
        "password": "SecurePass123",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_unknown_email(client: AsyncClient):
                                                        
    resp = await client.post("/api/v1/auth/forgot-password", json={
        "email": "nobody@example.com"
    })
    assert resp.status_code == 200
