import pytest
from unittest.mock import AsyncMock, patch

from app.agents.state import AgentState
from app.agents.answer_agent import answer_agent, SYSTEM_PROMPT

@pytest.mark.asyncio
@patch("app.agents.answer_agent._get_client")
async def test_edge_case_conflicting_sources(mock_get_client):
    mock_client = AsyncMock()

    class MockStream:
        async def __aiter__(self):
            class MockChoice:
                class MockDelta:
                    content = "The policy states 30 days [Source 1], but another section says 14 days [Source 2]."
                delta = MockDelta()

            class MockChunk:
                choices = [MockChoice()]
                usage = None
            yield MockChunk()

    mock_client.chat.completions.create.return_value = MockStream()
    mock_get_client.return_value = mock_client

    state: AgentState = {
        "query": "What is the return policy?",
        "query_type": "rag",
        "reranked_chunks": [
            {
                "content": "Returns are accepted within 30 days.",
                "metadata": {"filename": "policy_v1.txt"}
            },
            {
                "content": "All returns must be made within 14 days.",
                "metadata": {"filename": "policy_v2.txt"}
            }
        ],
        "history": []
    }

    result_state = await answer_agent(state)

    # Verify the prompt includes both sources
    call_args = mock_client.chat.completions.create.call_args[1]
    messages = call_args["messages"]

    assert "Source 1" in messages[0]["content"]
    assert "Source 2" in messages[0]["content"]
    assert "30 days" in messages[0]["content"]
    assert "14 days" in messages[0]["content"]

    assert result_state["agent_trace"]["answer"]["context_chunks"] == 2

@pytest.mark.asyncio
@patch("app.agents.answer_agent._get_client")
async def test_edge_case_noisy_data(mock_get_client):
    mock_client = AsyncMock()

    class MockStream:
        async def __aiter__(self):
            class MockChoice:
                class MockDelta:
                    content = "The total revenue was $500 [Source 1]."
                delta = MockDelta()

            class MockChunk:
                choices = [MockChoice()]
                usage = None
            yield MockChunk()

    mock_client.chat.completions.create.return_value = MockStream()
    mock_get_client.return_value = mock_client

    state: AgentState = {
        "query": "What was the total revenue?",
        "query_type": "rag",
        "reranked_chunks": [
            {
                "content": "adkfja kjdfkajd f Revenue: $500. dkfjadf",
                "metadata": {"filename": "scanned_doc.ocr"}
            },
        ],
        "history": []
    }

    result_state = await answer_agent(state)

    # Verify the prompt includes the noisy source
    call_args = mock_client.chat.completions.create.call_args[1]
    messages = call_args["messages"]

    assert "adkfja" in messages[0]["content"]
    assert "Revenue: $500" in messages[0]["content"]

    assert result_state["agent_trace"]["answer"]["context_chunks"] == 1
