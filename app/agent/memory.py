
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings


logger = logging.getLogger(__name__)


# Conversation memory: keep the thread short without damage.

def _blocks(message: dict[str, Any]) -> list[Any]:
    
    content = message.get("content")
    
    return content if isinstance(content, list) else []


def _block_type(block: Any) -> str | None:
    
    if isinstance(block, dict):
        return block.get("type")
    
    return getattr(block, "type", None)


def _block_attr(block: Any, name: str) -> Any:
    
    if isinstance(block, dict):
        return block.get(name)
    
    return getattr(block, name, None)


def _tool_use_ids(message: dict[str, Any]) -> set[str]:
    
    return {
        _block_attr(b, "id")
        for b in _blocks(message)
        if _block_type(b) == "tool_use" and _block_attr(b, "id")
    }


def _has_tool_use(message: dict[str, Any]) -> bool:
    
    return any(_block_type(b) == "tool_use" for b in _blocks(message))


def repair_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove orphaned tool_use // tool_result blocks from a sliced window."""
    available: set[str] = set()
    
    for message in messages:
        
        available |= _tool_use_ids(message)

    repaired: list[dict[str, Any]] = []
    
    for message in messages:
        
        blocks = _blocks(message)
        
        if message.get("role") == "user" and blocks:
            
            kept = [
                b for b in blocks
                if _block_type(b) != "tool_result"
                or _block_attr(b, "tool_use_id") in available
            ]
            
            if not kept:
                # The whole turn was orphaned tool results.
                continue
            
            if len(kept) != len(blocks):
                
                logger.debug("Dropped %d orphaned tool_result block(s)",
                             len(blocks) - len(kept)
                             )
                
                message = {**message, "content": kept}
                
        repaired.append(message)

    # A trailing assistant turn whose tool_use was never answered would make the
    # next request start mid-exchange.
    while repaired and repaired[-1].get("role") == "assistant" and _has_tool_use(repaired[-1]):
        logger.debug("Dropped trailing unanswered tool_use turn")
        repaired.pop()

    return repaired


# Tool results worth carrying for the whole conversation rather than letting
# them scroll out of the window.  
PINNED_TOOLS: frozenset[str] = frozenset({"query_pricing_batch"})


def _pinned_tool_indices(messages: list[dict[str, Any]]) -> list[int]:
    """Indices of the assistant/user pair carrying a pinned tool's result.

    Both halves are returned: an assistant `tool_use` kept without its
    `tool_result` (or the reverse) is exactly the orphan that 400s.
    """
    for i, message in enumerate(messages):
        
        if message.get("role") != "assistant":
            continue
        
        names = {
            _block_attr(b, "name")
            for b in _blocks(message)
            if _block_type(b) == "tool_use"
        }
        if not (names & PINNED_TOOLS):
            continue
        
        # The matching results are in the immediately following user turn.
        if i + 1 < len(messages) and messages[i + 1].get("role") == "user":
            
            return [i, i + 1]
        
    return []


def trim_history(
    messages: list[dict[str, Any]],
    *,
    max_messages: int | None = None,
    pin_tools: bool = True,
) -> list[dict[str, Any]]:
    """Keep the seed, the pinned pricing result, and the most recent messages.

    Returns a new list; the caller's history is never mutated, since the session
    store keeps the full transcript for audit even when the model sees a window.
    """
    limit = max_messages or get_settings().agent_memory_messages
    
    if len(messages) <= limit:
        return repair_pairs(list(messages))

    keep: list[int] = [0]  # the seed: which vehicle, which defects
    
    if pin_tools and get_settings().agent_pin_pricing:
        
        keep += _pinned_tool_indices(messages)

    tail_start = len(messages) - limit
    keep += range(tail_start, len(messages))

    # Deduplicate while preserving order -> the pinned pair may already sit
    # inside the tail on a short conversation.
    seen: set[int] = set()
    
    window = [
        messages[i] for i in keep
        if i < len(messages) and not (i in seen or seen.add(i))
    ]
    repaired = repair_pairs(window)

    logger.debug(
        "History trimmed: %d -> %d message(s) (limit %d, pinned %s)",
        len(messages), 
        len(repaired), 
        limit, 
        sorted(set(keep) - set(range(tail_start, len(messages)))),
    )
    
    return repaired



