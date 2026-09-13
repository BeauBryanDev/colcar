"""RTM rejection verdict: the legal floor and the binding A/B rule."""

from __future__ import annotations

from app.rag.rtm_rules import is_always_rejection, verdict, worst_rejection_class


def norma(clase: str | None, *, vinculante: bool = True, key: str = "vinculante"):
    return {key: vinculante, "clase_rechazo": clase}


def test_legal_floor_rejects_without_any_retrieval():
    result = verdict("lamp_broken", [])
    assert result["causal_rechazo"] is True
    assert result["clase_rechazo"] == "A"
    assert is_always_rejection("lamp_broken") is True


def test_legal_floor_keeps_the_retrieved_class_when_present():
    result = verdict("glass_shatter", [norma("B")])
    assert result["causal_rechazo"] is True
    assert result["clase_rechazo"] == "B"


def test_class_a_wins_over_class_b():
    assert worst_rejection_class([norma("B"), norma("A")]) == "A"
    assert worst_rejection_class([norma("B")]) == "B"
    assert worst_rejection_class([]) is None


def test_non_binding_clauses_never_reject():
    advisory = [norma("A", vinculante=False)]
    assert worst_rejection_class(advisory) is None
    assert verdict("crack", advisory)["causal_rechazo"] is False
    ## The raw chunk payload spells it binding.
    assert worst_rejection_class([norma("A", key="binding")]) == "A"


def test_no_rejection_clause_returns_a_clean_verdict():
    result = verdict("scratch", [norma(None)])
    assert result["causal_rechazo"] is False
    assert result["clase_rechazo"] is None
    assert result["nota"]
