"""Brand multipliers: baseline degradation and catalog shape."""

from __future__ import annotations

from app.rag.brand_index import (
    DEFAULT_INDEX,
    apply_index,
    brand_index,
    get_brand,
    list_brands,
    models_for,
)


def test_missing_or_unknown_brand_quotes_at_baseline():
    assert brand_index(None) == DEFAULT_INDEX
    assert brand_index("") == DEFAULT_INDEX
    assert brand_index("Marca Inventada") == DEFAULT_INDEX
    assert get_brand("Marca Inventada") is None


def test_known_brands_keep_their_distinct_index():
    assert brand_index("  dacia ") == brand_index("Dacia")
    assert brand_index("Dacia") < DEFAULT_INDEX
    assert brand_index("Rolls-Royce") > brand_index("Dacia")


def test_apply_index_returns_whole_pesos():
    assert apply_index(1_000_000, 1.5) == 1_500_000
    assert apply_index(577_501, 1.0) == 577_501
    assert apply_index(None, 2.0) == 0
    assert isinstance(apply_index(999_999, 0.75), int)


def test_catalog_lists_brands_with_their_own_models():
    brands = list_brands()
    assert len(brands) == 25
    assert "Logan" in models_for("Dacia")
    assert "Logan" not in models_for("Kia")
    assert models_for("Marca Inventada") == []
