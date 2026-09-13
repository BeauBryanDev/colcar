"""check_repair_prices: user-asked reference prices over the same trie."""

from __future__ import annotations

from app.agent.tools_iml import execute_tool
from app.rag.brand_index import brand_index
from app.rag.check_repair_prices import check_repair_prices
from app.rag.pricing_rag import get_trie


def _one(consulta: dict, brand: str | None = None) -> dict:
    return check_repair_prices([consulta], brand=brand)["consultas"][0]


def test_full_query_matches_the_inspection_quote_path():
    ## A hypothetical quote and a real one must come from the same node.
    row = _one({"pieza": "hood", "tipo_defecto": "dent", "severidad": "moderado"})
    assert row["resultados"][0]["fallback_level"] == "exact"
    node = get_trie().lookup("hood", "dent", "moderado").entry
    assert row["resultados"][0]["entry"]["total_cost_cop"] == node.total_cost_cop


def test_missing_severity_returns_all_three_levels():
    row = _one({"pieza": "back_left_door", "tipo_defecto": "scratch"})
    assert [r["severidad"] for r in row["resultados"]] == ["leve", "moderado", "grave"]
    ## Doors have no rows of their own: every level is a category estimate.
    assert all(r["fallback_level"] == "part_generic" for r in row["resultados"])
    assert all(r["precio_exacto"] is False for r in row["resultados"])


def test_legal_floor_defect_collapses_to_one_grave_row():
    row = _one({"pieza": "front_glass", "tipo_defecto": "glass_shatter"})
    assert len(row["resultados"]) == 1
    assert row["resultados"][0]["severidad"] == "grave"


def test_part_only_lists_services_via_the_category_node():
    row = _one({"pieza": "left_mirror"})
    assert row["resultados"]
    assert all(r["pieza"] == "left_mirror" for r in row["resultados"])
    assert all(r["fallback_level"] == "part_generic" for r in row["resultados"])


def test_unpriced_and_unknown_are_explicit_never_a_number():
    unpriced = _one({"pieza": "wheel", "tipo_defecto": "Puncture", "severidad": "leve"})
    assert unpriced["resultados"][0]["entry"] is None
    assert "cotizacion manual" in unpriced["nota"]

    unknown = _one({"pieza": "capo"})
    assert unknown["resultados"] == []
    assert "no reconocida" in unknown["nota"]


def test_brand_index_comes_from_context_and_is_applied():
    base = _one({"pieza": "hood", "tipo_defecto": "dent", "severidad": "grave"})
    bmw = execute_tool(
        "check_repair_prices",
        {"consultas": [{"pieza": "hood", "tipo_defecto": "dent", "severidad": "grave"}]},
        context={"brand": "BMW"},
    )
    b = base["resultados"][0]["entry"]["total_cost_cop"]
    p = bmw["consultas"][0]["resultados"][0]["entry"]["total_cost_cop"]
    assert p == round(b * brand_index("BMW"))
    assert bmw["resumen"]["indice_marca"] == brand_index("BMW")


def test_empty_input_asks_instead_of_pricing():
    result = execute_tool("check_repair_prices", {}, context={})
    assert result["consultas"] == []
    assert "consulta valida" in result["instrucciones"]
