import logging
import json
import re
from openai import AsyncOpenAI
from app.agents.state import AgentState
from app.config import settings

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None

def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
        )
    return _client

# ROUTER_FIX
# Regex fast-path: chitchat ONLY — do not add summarize here
CHITCHAT_PATTERN = re.compile(
    r"^(hello|hi|hey|xin chào|chào|alo|chào bạn|bạn khỏe|cảm ơn|thanks|thank you|ok|okay|bye|tạm biệt)[\s!?.]*$",
    re.IGNORECASE
)

CONFIDENCE_THRESHOLDS = {
    "rag":       0.70,
    "summarize": 0.72,
    "chitchat":  0.50,
    "clarify":   0.00,
}

REWRITER_PROMPT = """You are a query rewriter for a Vietnamese RAG chatbot. Your only job is to rewrite the user's current query to be self-contained and unambiguous, using the conversation history as context.

## Conversation history (last 3 turns):
{history}

## Current query:
{query}

## Rules:
- If the query is already self-contained → return it UNCHANGED, word for word
- If the query contains ambiguous pronouns ("nó", "cái đó", "vấn đề đó", "còn cái kia") → replace with the specific entity from history
- If the query is missing a subject or object that is clearly implied by history → add it
- Do NOT add information that is not present in the history
- Do NOT explain or add preamble — return only the rewritten query as a plain string

## Examples:
History: "Chính sách bảo hành sản phẩm A là 12 tháng"
Query: "Còn sản phẩm B thì sao?"
Output: Chính sách bảo hành sản phẩm B là gì?

History: "Hướng dẫn cài đặt Python trên Ubuntu"
Query: "Nó có chạy trên Windows không?"
Output: Python có chạy trên Windows không?

History: (empty)
Query: "Xin chào"
Output: Xin chào

## Output:"""

ROUTER_SYSTEM = """You are an intent classifier for a Vietnamese RAG chatbot. Classify the user query into exactly one of the intents below.

## Intent definitions:

**chitchat** — Casual conversation that requires no document lookup.
Examples: greetings, thanks, general comments, questions about the AI itself.

**summarize** — A request to summarize or synthesize content from documents or the conversation.
Examples: "tóm tắt lại", "tổng hợp các ý chính", "cho tôi overview về...", "điểm lại những gì đã nói".

**rag** — A specific factual question that requires retrieving information from the knowledge base.
Examples: questions about products, policies, procedures, technical specifications, internal guidelines.

**clarify** — The query is too vague or ambiguous to classify confidently, even with conversation history.

---

## Query to classify:
"{query}"

## Conversation history (last 3 turns):
{history}

---

## Output format:
Return ONLY valid JSON. No markdown, no explanation outside the JSON.

{{
  "intent": "<chitchat | summarize | rag | clarify>",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<one short sentence explaining the classification>"
}}

## Examples:
{{"intent": "rag", "confidence": 0.95, "reasoning": "User is asking for specific product warranty terms"}}
{{"intent": "chitchat", "confidence": 0.98, "reasoning": "Standard greeting, no document lookup needed"}}
{{"intent": "clarify", "confidence": 0.80, "reasoning": "Query is only two words with no clear subject or context"}}
{{"intent": "summarize", "confidence": 0.91, "reasoning": "User explicitly asked to summarize previous content"}}

## Output:"""

CLARIFY_PROMPT = """You are a helpful assistant. The user's query was too ambiguous to answer accurately.

## Original query:
"{query}"

## Why clarification is needed:
{reasoning}

## Instructions:
- Ask the user exactly ONE short, friendly follow-up question
- Be specific about what information you need to answer correctly
- Do not ask multiple things at once
- Do not apologize excessively
- Match the user's language (Vietnamese if they wrote in Vietnamese)

## Output:"""

# ROUTER_FIX
async def query_rewriter_node(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})
    query = state["query"].strip()
    history = state.get("history", [])

    # Get last 3 turns
    recent_history = history[-3:] if history else []

    if not recent_history:
        state["rewritten_query"] = query
        state["agent_trace"]["query_rewriter"] = "skipped (no history)"
        return state

    history_str = ""
    for h in recent_history:
        role = h.get("role", "unknown")
        content = h.get("content", "")
        history_str += f"{role.capitalize()}: {content}\n"

    try:
        client = _get_client()
        prompt = REWRITER_PROMPT.format(history=history_str.strip(), query=query)

        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            extra_headers={
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "RAG Query Rewriter",
            },
        )
        rewritten_query = resp.choices[0].message.content.strip()
        state["rewritten_query"] = rewritten_query
        state["agent_trace"]["query_rewriter"] = "rewritten"

    except Exception as e:
        log.error("Rewriter LLM error", extra={"error": str(e)})
        state["rewritten_query"] = query
        state["agent_trace"]["query_rewriter"] = f"error fallback: {str(e)}"

    return state

# ROUTER_FIX
async def clarify_node(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})
    query = state.get("query", "")
    reasoning = state.get("clarify_reasoning", "The query is ambiguous.")

    try:
        client = _get_client()
        prompt = CLARIFY_PROMPT.format(query=query, reasoning=reasoning)

        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            extra_headers={
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "RAG Clarify",
            },
        )
        clarify_msg = resp.choices[0].message.content.strip()
        state["response"] = clarify_msg
        state["agent_trace"]["clarify"] = "generated"

    except Exception as e:
        log.error("Clarify LLM error", extra={"error": str(e)})
        state["response"] = "Xin lỗi, tôi không hiểu rõ câu hỏi của bạn. Bạn có thể nói rõ hơn được không?"
        state["agent_trace"]["clarify"] = f"error fallback: {str(e)}"

    return state

# ROUTER_FIX
async def router_agent(state: AgentState) -> AgentState:
    state.setdefault("agent_trace", {})
    query = state.get("rewritten_query", state["query"]).strip()
    q_lower = query.lower()

    # Fast regex path
    if CHITCHAT_PATTERN.match(q_lower):
        state["query_type"] = "chitchat"
        state["router_confidence"] = 1.0
        state["router_reasoning"] = "Matched chitchat regex fast-path"
        state["agent_trace"]["router"] = "chitchat (regex)"
        return state

    history = state.get("history", [])
    recent_history = history[-3:] if history else []
    history_str = ""
    for h in recent_history:
        role = h.get("role", "unknown")
        content = h.get("content", "")
        history_str += f"{role.capitalize()}: {content}\n"
    if not history_str:
        history_str = "(empty)"

    # LLM fallback path
    try:
        client = _get_client()
        prompt = ROUTER_SYSTEM.format(query=query, history=history_str.strip())

        resp = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            extra_headers={
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "RAG Router",
            },
        )
        result_text = resp.choices[0].message.content.strip()
        print(f"DEBUG LLM OUTPUT: {result_text}")

        # Sometime LLMs output "```json ... ```" or just text.
        # Find the first { and the last }
        start_idx = result_text.find("{")
        end_idx = result_text.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            result_text = result_text[start_idx:end_idx+1]

        try:
            result_json = json.loads(result_text)
        except json.JSONDecodeError:
            log.error(f"Failed to parse JSON. Raw text: {result_text}")
            raise

        intent = result_json.get("intent", "rag").lower()
        confidence = float(result_json.get("confidence", 0.0))
        reasoning = result_json.get("reasoning", "No reasoning provided")

        if intent not in ["rag", "chitchat", "summarize", "clarify"]:
            intent = "rag"

        threshold = CONFIDENCE_THRESHOLDS.get(intent, 0.0)

        if confidence < threshold:
            state["query_type"] = "clarify"
            state["clarify_reasoning"] = f"Original intent {intent} had low confidence ({confidence} < {threshold}). {reasoning}"
            state["router_reasoning"] = state["clarify_reasoning"]
            state["agent_trace"]["router"] = f"clarify (low confidence {confidence})"
        else:
            state["query_type"] = intent
            if intent == "clarify":
                 state["clarify_reasoning"] = reasoning
            state["router_reasoning"] = reasoning
            state["agent_trace"]["router"] = f"{intent} (llm)"

        state["router_confidence"] = confidence

    except Exception as e:
        import traceback
        log.error(f"Router LLM error: {traceback.format_exc()}")
        # Safe default to chitchat on error
        state["query_type"] = "chitchat"
        state["router_confidence"] = 0.0
        state["router_reasoning"] = f"Error fallback: {str(e)}"
        state["agent_trace"]["router"] = "chitchat (error fallback)"

    return state
