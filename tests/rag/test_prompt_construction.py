import pytest
from unittest.mock import AsyncMock, patch

from app.agents.state import AgentState
from app.agents.answer_agent import answer_agent, SYSTEM_PROMPT

@pytest.mark.asyncio
@patch("app.agents.answer_agent._get_client")
async def test_prompt_construction_rag(mock_get_client):
    mock_client = AsyncMock()

    # Mocking the streaming response
    class MockStream:
        async def __aiter__(self):
            class MockChoice:
                class MockDelta:
                    content = "Test response"
                delta = MockDelta()

            class MockChunk:
                choices = [MockChoice()]
                usage = None

            yield MockChunk()

            class MockUsageChunk:
                choices = [MockChoice()]
                class MockUsage:
                    total_tokens = 42
                usage = MockUsage()

            yield MockUsageChunk()

    mock_client.chat.completions.create.return_value = MockStream()
    mock_get_client.return_value = mock_client

    state: AgentState = {
        "query": "What is the warranty period?",
        "query_type": "rag",
        "reranked_chunks": [
            {
                "content": "The warranty period is 12 months.",
                "metadata": {"filename": "warranty.pdf"}
            }
        ],
        "history": []
    }

    result_state = await answer_agent(state)

    # Verify the prompt was constructed correctly
    call_args = mock_client.chat.completions.create.call_args[1]
    messages = call_args["messages"]

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Context:\n[Source 1 - warranty.pdf]\nThe warranty period is 12 months." in messages[0]["content"]
    assert SYSTEM_PROMPT in messages[0]["content"]

    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "What is the warranty period?"

    assert result_state["response"] == "Test responseTest response"
    assert result_state["token_count"] == 42
    assert result_state["agent_trace"]["answer"]["context_chunks"] == 1

@pytest.mark.asyncio
@patch("app.agents.answer_agent._get_client")
async def test_prompt_construction_summarize(mock_get_client):
    mock_client = AsyncMock()

    # Mocking the streaming response
    class MockStream:
        async def __aiter__(self):
            class MockChoice:
                class MockDelta:
                    content = "Summary here."
                delta = MockDelta()

            class MockChunk:
                choices = [MockChoice()]
                usage = None

            yield MockChunk()

    mock_client.chat.completions.create.return_value = MockStream()
    mock_get_client.return_value = mock_client

    state: AgentState = {
        "query": "Summarize this document.",
        "query_type": "summarize",
        "reranked_chunks": [
            {
                "content": "Full document text...",
                "metadata": {"filename": "doc.txt"}
            }
        ],
        "history": []
    }

    await answer_agent(state)

    # Verify the summarize prompt
    call_args = mock_client.chat.completions.create.call_args[1]
    messages = call_args["messages"]

    assert messages[0]["role"] == "system"
    assert "=== DOCUMENT: doc.txt ===" in messages[0]["content"]
    assert "Full document text..." in messages[0]["content"]
    assert "You are an expert analyst." in messages[0]["content"]

@pytest.mark.asyncio
@patch("app.agents.answer_agent._get_client")
async def test_edge_case_no_context(mock_get_client):
    mock_client = AsyncMock()

    class MockStream:
        async def __aiter__(self):
            class MockChoice:
                class MockDelta:
                    content = "I don't know."
                delta = MockDelta()

            class MockChunk:
                choices = [MockChoice()]
                usage = None
            yield MockChunk()

    mock_client.chat.completions.create.return_value = MockStream()
    mock_get_client.return_value = mock_client

    state: AgentState = {
        "query": "What is the meaning of life?",
        "query_type": "rag",
        "reranked_chunks": [],  # Empty context
        "history": []
    }

    result_state = await answer_agent(state)

    # Verify the fallback prompt
    call_args = mock_client.chat.completions.create.call_args[1]
    messages = call_args["messages"]

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT  # No context added

    assert result_state["agent_trace"]["answer"]["context_chunks"] == 0
