
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.agent.system_prompt import CAR_LENS_SYSTEM_PROMPT
from app.agent.tools_iml import execute_tool
from app.agent.tools_schema import TOOLS
from app.core.config import get_settings
from app.core.exceptions import AgentError, AgentLoopLimitError, AppError

logger = logging.getLogger(__name__)

# The Claude Haiku tool-use loop.
# This is a loop that uses the Claude Haiku tool to generate a reply.
# A manual [[while stop_reason == "tool_use"]] loop
# Vision runs locally in
# ONNX, so Claude never receives an image, it reasons over the compact JSON the
# pipeline produced and calls two tools.
@dataclass
class AgentRun:
    """Outcome of one loop, including everything needed to resume later."""

    reply: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # Cache accounting. A caching regression is silent
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    stop_reason: str | None = None

    @property
    def tools_used(self) -> list[str]:
        return [c["name"] for c in self.tool_calls]

    def tool_result(self, 
                    name: str
                    ) -> dict[str, Any] | None:
        """Most recent result for a given tool, for building the report."""
        for call in reversed(self.tool_calls):
            
            if call["name"] == name:
                return call["result"]
            
        return None


# The Claude LLM Provider brain is a singleton.
def _client() -> anthropic.Anthropic:
    
    settings = get_settings()
    
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value()
    )


def _text_of(content: list[Any]) -> str:
    
    return "\n".join(
        
        block.text for block in content if getattr(block, "type", None) == "text"
    ).strip()


#  prompt caching

_CACHE_CONTROL = {"type": "ephemeral"}

# The prefix re-sent on every request is ~5.4k tokens (system ~2.7k + the eight
# tool schemas ~2.7k), and the loop re-sends it once per iteration. Caching it
# makes every turn after the first read it at 0.1x.
#
# Haiku 4.5 has a 4096-token MINIMUM cacheable prefix .

def _marked(message: dict[str, Any]) -> dict[str, Any]:
    
    """A copy of message with a cache breakpoint on its last content block."""
    content = message.get("content")
    
    if isinstance(content, str):
        return {
            **message,
            "content": [
                {"type": "text", 
                 "text": content, 
                 "cache_control": _CACHE_CONTROL}
            ],
        }
        
    if not isinstance(content, list) or not content:
        
        return message
    
    last = content[-1]
    if not isinstance(last, dict):
        # An SDK content object (an assistant turn) -- never mutate or rebuild
        # one; tool_use blocks must survive verbatim.
        return message
    
    return {**message, 
            "content": [*content[:-1], 
                        {**last, 
                         "cache_control": _CACHE_CONTROL}
                        ]
            }


def _stable_head_index(messages: list[dict[str, Any]]) -> int:
    """Where the byte-identical head of the window ends.

    trim_history returns [seed] + [pinned pricing pair] + [recent tail]. The
    seed and the pinned pair repeat unchanged every turn; the tail moves. So the
    breakpoint goes on the pinned pair's `tool_result` turn when it is in the
    window, and on the seed otherwise.
    """
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        
        if message.get("role") != "user":
            continue
        
        blocks = message.get("content")
        
        if isinstance(blocks, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks
        ):
            logger.debug(f"stable head index: {i}")
            return i
        
        logger.debug(f"stable head index: {i}")
        
    logger.debug(f"stable head index: {i}")
    
    return 0


def _request_kwargs(
    history: list[dict[str, Any]],
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one Messages request, with up to three cache breakpoints.

    Extracted from the loop so the markers can be asserted offline: the suite
    blocks sockets, so a test cannot reach the API to inspect a real request.
    """
    settings = get_settings()
    messages = list(history)

    if messages:
        # 2. the stable head, and 3. the last tool_result turn, so a second
        # iteration reads the first one's prefix instead of re-paying for it.
        marks = {_stable_head_index(messages), len(messages) - 1}
        
        for i in marks:
            
            if messages[i].get("role") == "user":
                messages[i] = _marked(messages[i])

    return {
        "model": settings.anthropic_model,
        "max_tokens": settings.anthropic_max_tokens,
        # tools + system, the bulk of the win.
        "system": [{
            "type": "text",
            "text": system or CAR_LENS_SYSTEM_PROMPT,
            "cache_control": _CACHE_CONTROL,
        }],
        "tools": tools if tools is not None else TOOLS,
        "messages": messages,
    }


def run_agent(
    messages: list[dict[str, Any]],
    *,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_iterations: int | None = None,
    context: dict[str, Any] | None = None,
) -> AgentRun:
    """Drive the tool-use loop until Claude stops calling tools.

    messages`is the full conversation so far and is not mutated; the extended
    copy comes back on `AgentRun.messages` for the caller to persist.

    context carries server-side facts the tools need but the model must not
    supply -> currently the vehicle brand, which scales catalog prices.
    """
    settings = get_settings()
    client = _client()
    limit = max_iterations or settings.anthropic_max_tool_iterations

    history: list[dict[str, Any]] = list(messages)
    run = AgentRun(reply="", messages=history)
    # A reduced toolset is enforced here too, not only by what the model sees:
    # execute_tool knows every tool, so a named-but-unoffered one must not run.
    allowed = {t["name"] for t in tools} if tools is not None else None

    for iteration in range(1, limit + 1):
        run.iterations = iteration
        
        try:
            response = client.messages.create(**_request_kwargs(history, system, tools))
            
        except anthropic.APIStatusError as exc:
            raise AgentError(
                log_message=f"Anthropic API error {exc.status_code}: {exc.message}"
            ) from exc
            
        except anthropic.APIConnectionError as exc:
            raise AgentError(
                detail="No se pudo conectar con el asistente. Intenta de nuevo.",
                log_message=f"Anthropic connection error: {exc}",
            ) from exc

        run.input_tokens += response.usage.input_tokens
        run.output_tokens += response.usage.output_tokens
        run.cache_read_tokens += getattr(response.usage, "cache_read_input_tokens", 0) or 0
        run.cache_write_tokens += (
            getattr(response.usage, 
                    "cache_creation_input_tokens", 0) or 0
        )
        run.stop_reason = response.stop_reason

        # Append the assistant turn verbatim -- tool_use blocks must survive
        # intact or the follow-up tool_result cannot be matched to them.
        history.append({"role": "assistant",
                        "content": response.content})

        if response.stop_reason != "tool_use":
            
            run.reply = _text_of(response.content)
            
            logger.info(
                "Agent finished in %d iteration(s); tools=%s; tokens in/out=%d/%d; "
                "cache read/write=%d/%d",
                iteration, run.tools_used or "none",
                run.input_tokens, run.output_tokens,
                run.cache_read_tokens, run.cache_write_tokens,
            )
            return run

        tool_results: list[dict[str, Any]] = []
        
        for block in response.content:
            
            if getattr(block, "type", None) != "tool_use":
                continue

            logger.info("Tool call: %s", block.name)
            try:
                if allowed is not None and block.name not in allowed:
                    logger.warning("Tool %s not in this session's toolset", block.name)
                    result = {
                        "error": "Esa herramienta no esta disponible en esta conversacion.",
                        "recuperable": False,
                    }
                    is_error = True
                else:
                    result = execute_tool(
                        block.name,
                        dict(block.input),
                        context
                    )
                    is_error = False
                
            except AppError as exc:
                # Degrade rather than abort: a failed compliance lookup should
                # still leave Claude able to deliver a diagnosis and a quote.
                logger.warning("Tool %s failed: %s", 
                               block.name, exc.log_message)
                
                result = {"error": exc.detail, "recuperable": True}
                is_error = True

            run.tool_calls.append(
                {"name": block.name,
                 "input": dict(block.input), 
                 "result": result
                 }
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False),
                **({"is_error": True} if is_error else {}),
            })

        # All results for a turn go back in ONE user message. Splitting them
        # trains the model out of making parallel tool calls.
        history.append({
            "role": "user", 
            "content": tool_results
            })

    raise AgentLoopLimitError(
        log_message=(
            f"tool loop hit {limit} iterations; tools called: {run.tools_used}"
        )
    )

# Appointment-only chats have no seed: /chat drives them through
# continue_conversation with APPOINTMENT_SYSTEM_PROMPT and APPOINTMENT_TOOLS.

def start_inspection_conversation(
    agent_payload: dict[str, Any], 
    *, 
    context: dict[str, Any] | None = None
) -> AgentRun:
    
    """Seed a new conversation with the vision result and get the report."""
    seed = (
        "Estos son los resultados de la inspeccion visual del vehiculo.\n\n"
        f"{json.dumps(agent_payload, ensure_ascii=False, indent=2)}\n\n"
        "Entrega el diagnostico completo: explica los danos encontrados, "
        "consulta el catalogo de precios y la normativa RTM, y presenta la "
        "cotizacion y la situacion legal del vehiculo."
    )
    return run_agent([
                    {"role": "user", 
                     "content": seed}
                    ], 
                     context=context)


def continue_conversation(
    messages: list[dict[str, Any]],
    user_message: str,
    *,
    context: dict[str, Any] | None = None,
    system: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> AgentRun:
    """Answer a follow-up question in an existing thread."""
    
    return run_agent(
        [*messages, 
         {"role": "user", 
          "content": user_message
          }
         ], 
        context=context,
        system=system,
        tools=tools,
    )



