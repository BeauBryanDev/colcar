"""Pricing trie: exact keys, fallback levels, floors, batch arithmetic."""

from __future__ import annotations

from app.rag.brand_index import brand_index
from app.rag.pricing_rag import query_pricing_batch


def test_catalog_loads_every_entry(trie):
    assert len(trie) == 67
    assert "generic:body_panel" in trie.piezas


def test_lookup_keys_are_the_raw_english_class_names(trie):
    assert trie.lookup("hood", "dent", "leve").fallback_level == "exact"
    ## Spanish keys belong to the compliance side, not here.
    assert trie.lookup("capo", "abolladura", "leve").entry is None


def test_exact_lookup_returns_the_catalog_entry(trie):
    result = trie.lookup("front_bumper", "scratch", "moderado")
    assert result.fallback_level == "exact"
    assert result.exact_match is True
    assert result.entry.total_cost_cop > 0


def test_missing_severity_falls_back_upward(tiny_trie):
    result = tiny_trie.lookup("hood", "dent", "moderado")
    assert result.fallback_level == "part+defect_generic"
    ## Equidistant between leve and grave: over-quote, never under-quote.
    assert result.entry.severidad == "grave"


def test_unknown_part_reaches_its_category_generic(trie):
    result = trie.lookup("back_left_door", "dent", "moderado")
    assert result.fallback_level == "part_generic"
    assert result.entry.pieza == "generic:body_panel"


def test_unpriced_combination_reports_not_found(trie):
    result = trie.lookup("wheel", "Puncture", "moderado")
    assert result.fallback_level == "not_found"
    assert result.entry is None


def test_severity_floor_applies_before_the_lookup(trie):
    result = trie.lookup("front_glass", "glass_shatter", "leve")
    assert result.severidad_applied == "grave"
    assert result.fallback_level == "exact"
    assert result.entry.severidad == "grave"


def test_batch_collapses_duplicates_and_sums_in_python():
    defects = [
        {"pieza": "hood", "tipo_defecto": "dent", "severidad": "leve"},
        {"pieza": "hood", "tipo_defecto": "dent", "severidad": "leve"},
        {"pieza": "wheel", "tipo_defecto": "Puncture", "severidad": "moderado"},
    ]
    result = query_pricing_batch(defects)
    priced = [i for i in result["items"] if i["entry"]]

    assert len(result["items"]) == 2
    assert priced[0]["cantidad"] == 2
    assert result["resumen"]["total_cop"] == priced[0]["subtotal_cop"]
    assert result["resumen"]["items_sin_precio"] == ["wheel/Puncture"]


def test_brand_scaling_keeps_the_breakdown_summing():
    defects = [{"pieza": "hood", "tipo_defecto": "dent", "severidad": "grave"}]
    baseline = query_pricing_batch(defects)["resumen"]
    premium = query_pricing_batch(defects, brand="BMW")["resumen"]

    assert premium["indice_marca"] == brand_index("BMW")
    assert premium["total_cop"] > baseline["total_cop"]
    assert premium["marca"]
    components = (
        premium["subtotal_mano_obra_cop"]
        + premium["subtotal_materiales_cop"]
        + premium["subtotal_repuestos_cop"]
    )
    assert abs(components - premium["total_cop"]) <= 2
