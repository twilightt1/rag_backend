import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agents.state import AgentState
from app.agents.graph import rag_graph

@pytest.mark.asyncio
@patch("app.agents.answer_agent._get_client")
@patch("app.agents.retrieval_agent.vector_search")
@patch("app.agents.retrieval_agent.bm25_search")
@patch("app.agents.memory_agent.memory_load_agent")
@patch("app.agents.memory_agent.memory_save_agent")
@patch("app.agents.router_agent.router_agent")
@patch("app.agents.hallucination_agent.hallucination_agent")
async def test_e2e_rag_query_flow(
    mock_hallucination, mock_router, mock_mem_save, mock_mem_load,
    mock_bm25, mock_vector, mock_get_client
):
    # Setup mocks
    state = {
        "query": "How do I configure the server?",
        "conversation_id": "test_conv",
        "history": [],
        "document_ids": None
    }

    # Mock the router deciding it's a RAG query
    async def mock_router_fn(s):
        s["query_type"] = "rag"
        return s
    mock_router.side_effect = mock_router_fn

    # Mock memory load
    async def mock_mem_load_fn(s):
        return s
    mock_mem_load.side_effect = mock_mem_load_fn

    # Mock retrieval
    mock_vector.return_value = [
        {"content": "Server configuration requires a settings.json file.", "metadata": {"filename": "manual.md"}, "score": 0.9, "source": "vector"}
    ]
    mock_bm25.return_value = []

    # Mock answer generation
    mock_client = AsyncMock()
    class MockStream:
        async def __aiter__(self):
            class MockChoice:
                class MockDelta:
                    content = "Server configuration requires a settings.json file [Source 1]."
                delta = MockDelta()
            class MockChunk:
                choices = [MockChoice()]
                usage = None
            yield MockChunk()

            class MockUsageChunk:
                choices = [MockChoice()]
                class MockUsage:
                    total_tokens = 50
                usage = MockUsage()
            yield MockUsageChunk()

    mock_client.chat.completions.create.return_value = MockStream()
    mock_get_client.return_value = mock_client

    # Mock hallucination grader
    async def mock_hall_fn(s):
        s["agent_trace"] = s.get("agent_trace", {})
        s["agent_trace"]["hallucination"] = {"hallucinated": False, "score": 1.0}
        return s
    mock_hallucination.side_effect = mock_hall_fn

    # Mock memory save
    async def mock_mem_save_fn(s):
        return s
    mock_mem_save.side_effect = mock_mem_save_fn

    # Execute the graph
    result = await rag_graph.ainvoke(state)

    # Verify flow
    assert result["query_type"] == "rag"
    assert len(result.get("retrieved_chunks", [])) > 0
    assert result["response"] == "Server configuration requires a settings.json file [Source 1].Server configuration requires a settings.json file [Source 1]."
    assert result["agent_trace"]["hallucination"]["hallucinated"] is False

@pytest.mark.asyncio
@patch("app.agents.answer_agent._get_client")
@patch("app.agents.retrieval_agent.vector_search")
@patch("app.agents.retrieval_agent.bm25_search")
@patch("app.agents.memory_agent.memory_load_agent")
@patch("app.agents.memory_agent.memory_save_agent")
@patch("app.agents.router_agent.router_agent")
@patch("app.agents.hallucination_agent.hallucination_agent")
async def test_e2e_chitchat_flow(
    mock_hallucination, mock_router, mock_mem_save, mock_mem_load,
    mock_bm25, mock_vector, mock_get_client
):
    # Setup mocks
    state = {
        "query": "Hello there!",
        "conversation_id": "test_conv",
        "history": [],
        "document_ids": None
    }

    # Mock the router deciding it's chitchat
    async def mock_router_fn(s):
        s["query_type"] = "chitchat"
        return s
    mock_router.side_effect = mock_router_fn

    # Mock answer generation
    mock_client = AsyncMock()
    class MockStream:
        async def __aiter__(self):
            class MockChoice:
                class MockDelta:
                    content = "Hi! How can I help you today?"
                delta = MockDelta()
            class MockChunk:
                choices = [MockChoice()]
                usage = None
            yield MockChunk()

    mock_client.chat.completions.create.return_value = MockStream()
    mock_get_client.return_value = mock_client

    # Mock hallucination grader
    async def mock_hall_fn(s):
        return s
    mock_hallucination.side_effect = mock_hall_fn

    # Mock memory save
    async def mock_mem_save_fn(s):
        return s
    mock_mem_save.side_effect = mock_mem_save_fn

    # Execute the graph
    result = await rag_graph.ainvoke(state)

    # Verify flow
    assert result["query_type"] == "chitchat"
    # Should skip memory and retrieval
    mock_mem_load.assert_not_called()
    mock_vector.assert_not_called()
    mock_bm25.assert_not_called()

    assert result["response"] == "Hi! How can I help you today?"
