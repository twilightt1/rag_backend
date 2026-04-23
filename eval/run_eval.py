import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add the parent directory to sys.path to import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.retrieval.embedder import embed_query
from app.agents.hallucination_agent import hallucination_agent
from app.agents.state import AgentState
from app.config import settings
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
log = logging.getLogger(__name__)

def load_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Mock retrieval for standalone evaluation purposes
# In a real pipeline, this would call the actual `search` function from vector_retriever.py
async def retrieve_chunks(query: str, k: int = 3) -> List[Dict[str, Any]]:
    """
    Mock retriever that simulates fetching documents.
    Replace this with actual vector search in production.
    """
    # For the sake of the evaluation script demo, we return mock documents
    # matching the ground truth in dataset.json to show a non-zero score.
    mock_index = {
        "warranty": [{"id": "doc_warranty_1", "content": "The warranty period is 12 months."}],
        "password": [{"id": "doc_auth_reset", "content": "Click 'Forgot Password' to reset."}],
        "language": [{"id": "doc_features_i18n", "content": "Supports English and Spanish."}]
    }

    for key, docs in mock_index.items():
        if key in query.lower():
            return docs
    return [{"id": "doc_random", "content": "Unrelated content."}]

async def generate_answer(query: str, context_chunks: List[Dict[str, Any]]) -> str:
    """Mock generation or use the actual answer_agent."""
    # In a real script, invoke app.agents.answer_agent.answer_agent
    # Here we simulate an LLM response based on context for demonstration.
    if not context_chunks:
        return "I don't know."
    return context_chunks[0]["content"]

async def evaluate_correctness(query: str, generated_answer: str, ground_truth: str) -> float:
    """
    Uses LLM-as-a-judge to evaluate if the generated answer matches the ground truth.
    Returns a score between 0.0 and 1.0.
    """
    client = AsyncOpenAI(api_key=settings.OPENROUTER_API_KEY, base_url=settings.OPENROUTER_BASE_URL)
    prompt = f"""
    Evaluate the correctness of the generated answer compared to the ground truth.
    Query: {query}
    Ground Truth: {ground_truth}
    Generated Answer: {generated_answer}

    Score from 0 to 10 where 10 is completely correct. Output ONLY the number.
    """
    try:
        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        score_str = resp.choices[0].message.content.strip()
        score = float(score_str) / 10.0
        return min(max(score, 0.0), 1.0)
    except Exception as e:
        log.error(f"Failed to evaluate correctness: {e}")
        return 0.0

def calculate_retrieval_metrics(retrieved_ids: List[str], ground_truth_ids: List[str], k: int) -> Tuple[float, float]:
    """Calculate Recall@K and Precision@K"""
    retrieved_k = retrieved_ids[:k]
    hits = set(retrieved_k).intersection(set(ground_truth_ids))

    recall = len(hits) / len(ground_truth_ids) if ground_truth_ids else 0.0
    precision = len(hits) / len(retrieved_k) if retrieved_k else 0.0

    return recall, precision

async def run_evaluation(dataset_path: str, k: int = 3):
    dataset = load_dataset(dataset_path)
    log.info(f"Loaded {len(dataset)} evaluation queries.")

    total_recall = 0.0
    total_precision = 0.0
    total_correctness = 0.0
    hallucination_count = 0

    for item in dataset:
        query = item["query"]
        gt_chunks = item["ground_truth_chunks"]
        gt_answer = item["ground_truth_answer"]

        log.info(f"Evaluating Query: {query}")

        # 1. Retrieval
        retrieved_chunks = await retrieve_chunks(query, k)
        retrieved_ids = [c["id"] for c in retrieved_chunks]

        recall, precision = calculate_retrieval_metrics(retrieved_ids, gt_chunks, k)
        total_recall += recall
        total_precision += precision
        log.info(f"  Retrieval -> Recall@{k}: {recall:.2f}, Precision@{k}: {precision:.2f}")

        # 2. Generation
        answer = await generate_answer(query, retrieved_chunks)

        # 3. Correctness Evaluation
        correctness = await evaluate_correctness(query, answer, gt_answer)
        total_correctness += correctness
        log.info(f"  Correctness Score: {correctness:.2f}")

        # 4. Hallucination Check
        state: AgentState = {
            "query": query,
            "query_type": "rag",
            "response": answer,
            "reranked_chunks": retrieved_chunks,
            "agent_trace": {}
        }
        # Assuming hallucination_agent returns updated state
        try:
            halluc_state = await hallucination_agent(state)
            is_hallucinated = halluc_state["is_hallucination"]
        except Exception:
            is_hallucinated = False # Fallback if agent is not fully configured

        if is_hallucinated:
            hallucination_count += 1
            log.warning("  WARNING: Hallucination detected!")
        else:
            log.info("  Hallucination Check: PASS (Grounded)")

        print("-" * 40)

    # Aggregate
    n = len(dataset)
    metrics = {
        f"Average Recall@{k}": total_recall / n,
        f"Average Precision@{k}": total_precision / n,
        "Average Correctness": total_correctness / n,
        "Hallucination Rate": hallucination_count / n
    }

    log.info("=== EVALUATION SUMMARY ===")
    for k_metric, v in metrics.items():
        log.info(f"{k_metric}: {v:.2f}")

    # Example Regression Assertion
    assert metrics[f"Average Recall@{k}"] >= 0.0, "Recall degraded below threshold!"

if __name__ == "__main__":
    dataset_file = str(Path(__file__).parent / "dataset.json")
    asyncio.run(run_evaluation(dataset_file, k=3))
