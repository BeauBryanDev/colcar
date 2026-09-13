"""Catalog sources (v2): Mongo is the source of truth, JSON the fallback.

Offline: the Mongo readers are monkeypatched; `mongodb_uri` is unset in the
test settings, and the conftest `no_network` fixture would fail any socket.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr
from pymongo.errors import ServerSelectionTimeoutError

from app.rag import brand_index, pricing_rag
from app.rag.pricing_rag import build_trie
from scripts.seed_catalog import brand_docs, pricing_docs, trie_signature


@pytest.fixture
def mongo_configured(settings, monkeypatch):
    monkeypatch.setattr(
        settings, "mongodb_uri", SecretStr("mongodb://u:p@example.invalid/")
    )
    return settings


def test_without_a_uri_the_file_is_used_and_mongo_is_never_read(monkeypatch):
    def fail(*a, **k):
        pytest.fail("Mongo must not be read when MONGODB_URI is unset")

    monkeypatch.setattr(pricing_rag, "_entries_from_mongo", fail)
    trie = build_trie()
    assert trie.source == "json"
    assert len(trie) == 67


def test_mongo_entries_build_the_same_trie_as_the_file(
    mongo_configured, monkeypatch
):
    ## The parity check the seed script's --verify runs, without a cluster.
    file_entries = pricing_rag._entries_from_file()
    monkeypatch.setattr(
        pricing_rag, "_entries_from_mongo", lambda: list(file_entries)
    )
    from_mongo = build_trie()
    from_file = build_trie(mongo_configured.pricing_catalog_path)
    assert from_mongo.source == "mongo"
    assert from_file.source == "json"
    assert trie_signature(from_mongo) == trie_signature(from_file)


def test_unreachable_mongo_falls_back_to_json_loudly(
    mongo_configured, monkeypatch, caplog
):
    def down():
        raise ServerSelectionTimeoutError("no primary")

    monkeypatch.setattr(pricing_rag, "_entries_from_mongo", down)
    with caplog.at_level(logging.ERROR, logger="app.rag.pricing_rag"):
        trie = build_trie()
    assert trie.source == "json"
    assert len(trie) == 67
    assert any("falling back to JSON" in r.message for r in caplog.records)


def test_empty_collection_falls_back_rather_than_quoting_nothing(
    mongo_configured, monkeypatch
):
    monkeypatch.setattr(pricing_rag, "_entries_from_mongo", lambda: [])
    trie = build_trie()
    assert trie.source == "json"
    assert len(trie) == 67


def test_explicit_mongo_source_raises_instead_of_hiding_the_failure(
    mongo_configured, monkeypatch
):
    ## --verify must never compare the file with itself.
    monkeypatch.setattr(pricing_rag, "_entries_from_mongo", lambda: [])
    with pytest.raises(ValueError):
        build_trie(source="mongo")


def test_brand_index_falls_back_to_json(mongo_configured, monkeypatch):
    def down():
        raise ServerSelectionTimeoutError("no primary")

    monkeypatch.setattr(brand_index, "_brands_from_mongo", down)
    brand_index._load.cache_clear()
    try:
        assert brand_index.brand_index("Dacia") < 1.0
        assert brand_index.loaded_source() == "json"
    finally:
        brand_index._load.cache_clear()


def test_seed_docs_carry_stable_ids():
    p = pricing_docs(pricing_rag._entries_from_file())
    assert len(p) == 67
    assert all(d["_id"] == d["id"] for d in p)
    assert len({d["_id"] for d in p}) == 67

    b = brand_docs(brand_index._brands_from_file())
    assert len(b) == 25
    assert all(d["_id"] == d["brand"].lower() for d in b)
    assert len({d["_id"] for d in b}) == 25
