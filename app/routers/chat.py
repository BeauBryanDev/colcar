
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.agent.claude_agent import continue_conversation
from app.agent.system_prompt import APPOINTMENT_SYSTEM_PROMPT
from app.agent.tools_schema import APPOINTMENT_TOOLS
from app.agent.memory import trim_history
from app.core.config import get_settings
from app.core.exceptions import RateLimitError, SessionStateError
from app.core.rate_limit import limit_chat, limit_session_start
from app.core.session import session_store
from app.schemas.agent import ChatRequest, ChatResponse
from app.schemas.inspection import StartInspectionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspections", tags=["chat"])

# Chat with Car-Lens about an inspection.

# POST /api/inspections/chat   {session_id, message} -> {reply, timestamp}

def _now_iso() -> str:
    
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@router.post("/appointment-chat/start", 
             response_model=StartInspectionResponse,
             status_code=201,
             dependencies=[Depends(limit_session_start)])
async def start_appointment_chat() -> StartInspectionResponse:
    """Create a chat-only session for managing an existing booking."""
    session = session_store.create(mode="appointment")

    return StartInspectionResponse(
        session_id=session.id,
        message="Sesion de gestion de cita creada.",
    )


@router.post("/chat", response_model=ChatResponse,
             dependencies=[Depends(limit_chat)])
async def chat(payload: ChatRequest) -> ChatResponse:
    """Answer a follow-up question in an existing inspection thread."""
    # Raises SessionNotFoundError -> 404 {detail} for an expired session.
    session = session_store.get(payload.session_id)

    # Counted before the call, so a failing turn still uses one up and a
    # retry loop cannot run forever on one session.
    max_turns = get_settings().chat_max_turns_per_session
    if session_store.count_chat_turn(payload.session_id) > max_turns:
        raise RateLimitError(
            detail=(
                "Esta conversacion alcanzo su limite de mensajes. "
                "Inicia una nueva sesion para continuar."
            ),
            code="limite_conversacion",
            retry_after=60,
            log_message=f"session {payload.session_id} passed {max_turns} turns",
        )

    # Bounded window, seed pinned, tool_use/tool_result pairs kept intact.
    history = trim_history(session.messages)
    if not history:
        # No inspection has been seeded yet. Rather than fail, answer with the
        # conversation starting here -- the system prompt still applies.
        logger.info(
            "Chat on session %s before any inspection ran.", 
            payload.session_id
        )

    appointment_only = session.mode == "appointment"

    run = await run_in_threadpool(
        lambda: continue_conversation(
            history, 
            payload.message,
            context=session.agent_context(),
            system=APPOINTMENT_SYSTEM_PROMPT if appointment_only else None,
            tools=APPOINTMENT_TOOLS if appointment_only else None,
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
    #   E277E1  ,  GTH564 , 

 
    return ChatResponse(
        reply=run.reply,
        timestamp=_now_iso(),
        session_id=payload.session_id,
    )
