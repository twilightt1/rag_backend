# RAG Evaluation Framework

This directory contains the testing and evaluation framework for measuring the performance, reliability, and accuracy of the RAG system.

## Components

1. **Automated Test Cases (`dataset.json`)**
   - A JSON file containing a curated "golden dataset" of realistic user queries.
   - Each entry defines the `query`, the `ground_truth_chunks` (expected document chunk IDs that contain the answer), and the `ground_truth_answer` (the ideal response).

2. **Evaluation Script (`run_eval.py`)**
   - An automated script that simulates the RAG pipeline against the `dataset.json`.
   - **Metrics Calculated**:
     - `Recall@k`: Measures whether the expected ground truth chunks were successfully retrieved in the top `k` results.
     - `Precision@k`: Measures the proportion of the retrieved top `k` results that were actually relevant (in the ground truth set).
     - `Correctness`: Uses an LLM-as-a-judge approach to grade the generated answer against the ground truth answer on a scale from 0 to 1 (normalized from 0-10).
     - `Hallucination Check`: Passes the generated answer and retrieved context to the system's `hallucination_agent` to ensure the answer is fully grounded in the retrieved facts.

## Running the Evaluation

To run the offline evaluation against the golden dataset:

```bash
python eval/run_eval.py
```

*Note: Ensure your environment variables (like `OPENROUTER_API_KEY` or `OPENAI_API_KEY` depending on your config) are set, as the script uses the LLM for correctness judging and hallucination checks.*

## Continuous Evaluation Strategy

To ensure the RAG system remains reliable over time, implement the following continuous evaluation practices:

### 1. Offline Evaluation (CI/CD)
- **Regression Testing**: Integrate `run_eval.py` into your CI/CD pipeline (e.g., GitHub Actions). Set minimum threshold assertions (e.g., `assert avg_recall >= 0.85`). If a change to the chunking strategy, embedding model, or prompt drops recall or correctness below the threshold, the build should fail.
- **Dataset Expansion**: Continuously add failed or complex real-world queries from production into `dataset.json` to prevent future regressions.

### 2. Online Monitoring (Production)
- **User Feedback**: Implement explicit feedback mechanisms (thumbs up/down) on generated answers in the UI.
- **Implicit Signals**: Track metrics like session length, follow-up clarification queries, and copy-to-clipboard events to gauge answer utility.
- **Shadow Evaluation**: Sample a percentage of production queries and run them through the `hallucination_agent` asynchronously to monitor the live hallucination rate on a dashboard (e.g., using Datadog, Grafana, or LangSmith).

### 3. Periodic A/B Testing
- When testing a new embedding model, chunking size, or LLM, deploy it to a small percentage of traffic (e.g., 5%) and compare the online user feedback and shadow evaluation metrics against the control group before fully rolling out the change.