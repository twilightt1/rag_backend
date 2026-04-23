import pytest
from unittest.mock import AsyncMock, patch

from app.agents.hallucination_agent import hallucination_agent
from app.agents.state import AgentState

@pytest.mark.asyncio
@patch("app.agents.hallucination_agent._get_client")
async def test_hallucination_detection_pass(mock_get_client):
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(message=AsyncMock(content='{"is_grounded": true, "answers_question": true}'))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    state: AgentState = {
        "query": "What color is the sky?",
        "query_type": "rag",
        "response": "The sky is blue [Source 1].",
        "reranked_chunks": [
            {"content": "The sky is blue today.", "metadata": {"filename": "weather.txt"}}
        ],
        "agent_trace": {}
    }

    result = await hallucination_agent(state)

    assert result["agent_trace"]["hallucination"]["grounded"] is True
    assert result["is_hallucination"] is False

@pytest.mark.asyncio
@patch("app.agents.hallucination_agent._get_client")
async def test_hallucination_detection_fail(mock_get_client):
    mock_client = AsyncMock()
    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(message=AsyncMock(content='{"is_grounded": false, "answers_question": true, "fallback_message": "Tôi không tìm thấy thông tin về vấn đề này trong tài liệu."}'))
    ]
    mock_client.chat.completions.create.return_value = mock_response
    mock_get_client.return_value = mock_client

    state: AgentState = {
        "query": "What color is the sky?",
        "query_type": "rag",
        "response": "The sky is green [Source 1].",
        "reranked_chunks": [
            {"content": "The sky is blue today.", "metadata": {"filename": "weather.txt"}}
        ],
        "agent_trace": {}
    }

    result = await hallucination_agent(state)

    assert result["agent_trace"]["hallucination"]["grounded"] is False
    assert result["is_hallucination"] is True

@pytest.mark.asyncio
async def test_retrieval_recall_precision_mocked():
    # This is a simulated evaluation test to demonstrate how one would
    # evaluate recall@k and precision@k in a CI pipeline using a golden dataset.

    # 1. Golden Dataset: (Query, Ground Truth Document IDs)
    dataset = [
        ("How to install the software?", ["doc_install_1", "doc_install_2"]),
        ("What are the pricing tiers?", ["doc_pricing_1"]),
    ]

    # 2. Mocked Retrieval Function (Simulating a retriever returning some results)
    async def mock_retrieve(query, k):
        if "install" in query:
            return [{"id": "doc_install_1"}, {"id": "doc_irrelevant"}] # Retrieved 2, 1 is correct
        elif "pricing" in query:
            return [{"id": "doc_pricing_1"}, {"id": "doc_pricing_2"}] # Retrieved 2, both correct (assuming doc_pricing_2 is also good, but only 1 in GT)
        return []

    # 3. Evaluation Logic
    total_recall = 0
    total_precision = 0

    k = 2
    for query, ground_truth in dataset:
        results = await mock_retrieve(query, k)
        retrieved_ids = [res["id"] for res in results]

        # Calculate hits
        hits = set(retrieved_ids).intersection(set(ground_truth))

        # Recall = Hits / Total Ground Truth
        recall = len(hits) / len(ground_truth) if ground_truth else 0
        total_recall += recall

        # Precision = Hits / Total Retrieved
        precision = len(hits) / len(retrieved_ids) if retrieved_ids else 0
        total_precision += precision

    avg_recall = total_recall / len(dataset)
    avg_precision = total_precision / len(dataset)

    assert avg_recall > 0.0
    assert avg_precision > 0.0
    # In a real scenario, you'd assert against a threshold
    # assert avg_recall >= 0.8
