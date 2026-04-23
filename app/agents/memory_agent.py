import json, logging
from app.agents.state import AgentState
from app.redis_client import get_redis

log = logging.getLogger(__name__)

async def memory_load_agent(state: AgentState) -> AgentState:
    cid = state["conversation_id"]
    redis = await get_redis()
    cached = await redis.get(f"conv_history:{cid}")
    if cached:
        state["history"] = json.loads(cached)
        return state
    try:
        from sqlalchemy import select
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Message).where(Message.conversation_id == cid)
                .order_by(Message.created_at.desc()).limit(10)
            )
            msgs = result.scalars().all()
        history = [{"role": m.role, "content": m.content} for m in reversed(msgs)]
        state["history"] = history
        await redis.setex(f"conv_history:{cid}", 300, json.dumps(history))
    except Exception as e:
        log.warning("History load failed", extra={"error": str(e)})
        state["history"] = []
    return state

async def memory_save_agent(state: AgentState) -> AgentState:
    cid = state["conversation_id"]
    try:
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        async with AsyncSessionLocal() as db:
            db.add(Message(conversation_id=cid, role="user", content=state["query"]))
            db.add(Message(conversation_id=cid, role="assistant", content=state["response"],
                           agent_trace=state.get("agent_trace", {})))
            await db.commit()
        redis = await get_redis()
        await redis.delete(f"conv_history:{cid}")
    except Exception as e:
        log.error("Save messages failed", extra={"error": str(e)})
    return state
