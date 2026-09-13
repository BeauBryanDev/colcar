
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.agent.claude_agent import continue_conversation
from app.agent.memory import trim_history
from app.core.exceptions import SessionStateError
from app.core.session import session_store
from app.schemas.agent import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspections", tags=["chat"])

# Chat with Car-Lens about an inspection.

# POST /api/inspections/chat   {session_id, message} -> {reply, timestamp}

# Serving this well for the SPA needs more care than the shape suggests,
# because the SPA is a back-office tool and the session is not created until
# the user clicks "Run". The SPA can't know the session id until the user
# clicks "Run", so it has to send the message and the session id in the same
# request. The SPA can't know the session id until the user clicks "Run", so
# it has to send the message and the session id in the same request.
# TODO :  Must to edit this module later on,  just becuase an existing customer would like
# to talk to the agent in order to change the date of his appointment.
# Right now user will have to re upload his car image again to talk to agent. no UI/UX-friendly.

def _now_iso() -> str:
    
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    """Answer a follow-up question in an existing inspection thread."""
    # Raises SessionNotFoundError -> 404 {detail} for an expired session.
    session = session_store.get(payload.session_id)

    # Bounded window, seed pinned, tool_use/tool_result pairs kept intact.
    history = trim_history(session.messages)
    if not history:
        # No inspection has been seeded yet. Rather than fail, answer with the
        # conversation starting here -- the system prompt still applies.
        logger.info(
            "Chat on session %s before any inspection ran.", 
            payload.session_id
        )

    run = await run_in_threadpool(
        lambda: continue_conversation(
            history, 
            payload.message,
            context=session.agent_context()
        )
    )

    if not run.reply:
       
        raise SessionStateError(
            detail="El asistente no pudo generar una respuesta. Intenta de nuevo.",
            log_message=(
                f"empty reply, stop_reason={run.stop_reason}, "
                f"iterations={run.iterations}"
            ),
        )

    # Persist the whole exchange so the next turn continues from here. Storing
    # run.messages (not just the reply) keeps tool_use/tool_result blocks
    # paired -> the API rejects a history where they are split.
    # Persist only what this turn added. `history` is a trimmed view, so the
    # new messages are counted from its length, not the session's.
    session_store.append_messages(
        payload.session_id, 
        run.messages[len(history):]
    )

    logger.info(
        "Chat on %s: %d iteration(s), tools=%s, tokens=%d/%d, cache read/write=%d/%d",
        payload.session_id, run.iterations, run.tools_used or "none",
        run.input_tokens, run.output_tokens,
        run.cache_read_tokens, run.cache_write_tokens,
    )
    
    return ChatResponse(
        reply=run.reply,
        timestamp=_now_iso(),
        session_id=payload.session_id,
    )
