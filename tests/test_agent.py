"""Agent layer: memory window repair, tool dispatch, prompt consistency."""

from __future__ import annotations

import json
import re

import pytest

from app.agent import tools_iml
from app.agent.claude_agent import _request_kwargs
from app.agent.memory import repair_pairs, trim_history
from app.agent.system_prompt import CAR_LENS_SYSTEM_PROMPT
from app.agent.tools_iml import TOOL_IMPLEMENTATIONS, execute_tool
from app.agent.tools_schema import TOOL_NAMES, TOOLS


def test_repair_drops_orphaned_blocks(msg_user, msg_tool_use, msg_tool_result):
    orphan_result = repair_pairs([msg_user(), msg_tool_result("toolu_gone")])
    assert len(orphan_result) == 1
    assert orphan_result[0]["content"][0]["type"] == "text"

    trailing = repair_pairs([msg_user(), msg_tool_use("toolu_1")])
    assert len(trailing) == 1
    assert trailing[0]["role"] == "user"


def test_short_history_is_returned_untouched(msg_user, msg_assistant):
    history = [msg_user("seed"), msg_assistant("ok")]
    window = trim_history(history, max_messages=5)
    assert window == history
    assert window is not history
    assert len(history) == 2


def test_long_history_keeps_the_seed_and_the_tail(msg_user, msg_assistant):
    history = [msg_user("seed")]
    for i in range(10):
        history.append(msg_assistant(f"a{i}"))
        history.append(msg_user(f"u{i}"))

    window = trim_history(history, max_messages=4, pin_tools=False)
    assert window[0] == history[0]
    assert window[-1] == history[-1]
    assert len(window) == 5


def test_pricing_pair_is_pinned_as_a_pair(
    msg_user, msg_assistant, msg_tool_use, msg_tool_result
):
    history = [
        msg_user("seed"),
        msg_tool_use("toolu_price"),
        msg_tool_result("toolu_price"),
    ]
    for i in range(8):
        history.append(msg_user(f"u{i}"))
        history.append(msg_assistant(f"a{i}"))

    window = trim_history(history, max_messages=4)
    kept = [m for m in window if m in (history[1], history[2])]
    assert len(kept) == 2


def test_unknown_tool_returns_an_error_instead_of_raising():
    result = execute_tool("schedule_appointment", {})
    assert "error" in result
    assert sorted(TOOL_IMPLEMENTATIONS) == result["tools_disponibles"]


def test_compliance_routes_cosmetic_defects_without_touching_the_encoder(
    monkeypatch,
):
    def fail(*args, **kwargs):
        pytest.fail("compliance retrieval must not run for cosmetic defects")

    monkeypatch.setattr(tools_iml, "_query_compliance", fail)
    cosmetic = tools_iml.run_query_compliance(
        {"defects": [{"pieza": "back_left_door", "tipo_defecto": "scratch",
                      "severidad": "leve"}]}
    )
    entry = cosmetic["resultados"][0]
    assert entry["aplica_rtm"] is False
    assert entry["normas"] == []
    assert entry["causal_rechazo"] is False
    assert cosmetic["rechazo_rtm_probable"] is False

    ## The legal floor still rejects when retrieval returns nothing.
    monkeypatch.setattr(tools_iml, "_query_compliance", lambda *a, **k: [])
    floor = tools_iml.run_query_compliance(
        {"defects": [{"pieza": "front_left_light", "tipo_defecto": "lamp_broken",
                      "severidad": "grave"}]}
    )
    assert floor["resultados"][0]["causal_rechazo"] is True
    assert floor["rechazo_rtm_probable"] is True


def test_prompt_only_names_tools_that_exist():
    named = {
        name for name in re.findall(r"[a-z_]{6,}", CAR_LENS_SYSTEM_PROMPT)
        if name.startswith(("query_", "schedule_", "create_", "make_", "check_"))
    }
    assert named
    assert named <= TOOL_NAMES
    assert TOOL_NAMES == frozenset(TOOL_IMPLEMENTATIONS)
    ## The rules added after live failures must stay in the prompt.
    assert "NO uses emojis" in CAR_LENS_SYSTEM_PROMPT


#  prompt caching: the breakpoints that keep every turn off full price

def _breakpoints(kwargs: dict) -> int:
    n = sum(1 for b in kwargs["system"] if "cache_control" in b)
    for message in kwargs["messages"]:
        content = message.get("content")
        if isinstance(content, list):
            n += sum(
                1 for b in content if isinstance(b, dict) and "cache_control" in b
            )
    return n


def _cached_history(msg_user, msg_assistant, msg_tool_use, msg_tool_result):
    return [
        msg_user("seed"),
        msg_tool_use("toolu_price"),
        msg_tool_result("toolu_price"),
        msg_assistant("cotizacion"),
        msg_user("y el vidrio?"),
    ]


def test_tools_and_system_are_cached_together_without_altering_the_prompt(msg_user):
    """Haiku 4.5's minimum cacheable prefix is 4096 tokens and the system prompt
    alone is ~2.7k: only tools + system together clear it."""
    kwargs = _request_kwargs([msg_user("hola")])
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Caching must not change a single byte of the prompt itself.
    assert kwargs["system"][0]["text"] == CAR_LENS_SYSTEM_PROMPT


def test_the_stable_head_is_marked_and_the_api_limit_is_respected(
    msg_user, msg_assistant, msg_tool_use, msg_tool_result
):
    history = _cached_history(msg_user, msg_assistant, msg_tool_use, msg_tool_result)
    kwargs = _request_kwargs(history)
    assert _breakpoints(kwargs) <= 4          # hard API cap
    # The pinned pricing result is the last byte-identical point of the window.
    assert "cache_control" in kwargs["messages"][2]["content"][-1]


def test_two_identical_builds_produce_identical_bytes(
    msg_user, msg_assistant, msg_tool_use, msg_tool_result
):
    """The anti-invalidator test: a datetime or uuid creeping into the prefix
    would silently cost full price on every request."""
    history = _cached_history(msg_user, msg_assistant, msg_tool_use, msg_tool_result)
    first = json.dumps(_request_kwargs(history), sort_keys=True, default=str)
    second = json.dumps(_request_kwargs(history), sort_keys=True, default=str)
    assert first == second


def test_the_stored_transcript_is_never_marked(
    msg_user, msg_assistant, msg_tool_use, msg_tool_result
):
    """`run.messages` is persisted and re-trimmed every turn; a marker written
    into it would linger mid-history and drift as the window slides."""
    history = _cached_history(msg_user, msg_assistant, msg_tool_use, msg_tool_result)
    _request_kwargs(history)
    dumped = json.dumps(history, default=str)
    assert "cache_control" not in dumped


def test_the_model_sees_exactly_what_it_saw_before_caching(
    msg_user, msg_assistant, msg_tool_use, msg_tool_result
):
    """Saving money must not change a single word the model reads.

    `cache_control` is metadata, not content: strip the markers back out and
    the request must equal the pre-caching one -- same prompt, same tools,
    same messages, in the same order.
    """
    history = _cached_history(msg_user, msg_assistant, msg_tool_use, msg_tool_result)
    kwargs = _request_kwargs(history)

    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != "cache_control"}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    # System: one block carrying the unchanged prompt.
    assert [strip(b) for b in kwargs["system"]] == [
        {"type": "text", "text": CAR_LENS_SYSTEM_PROMPT}
    ]
    # Tools: the same list object the loop always sent.
    assert kwargs["tools"] is TOOLS
    # Messages: identical, except a plain-string turn is now an equivalent
    # single text block (the same bytes once rendered).
    for before, after in zip(history, strip(kwargs["messages"])):
        expected = (
            {**before, "content": [{"type": "text", "text": before["content"]}]}
            if isinstance(before["content"], str) else before
        )
        assert after == expected
