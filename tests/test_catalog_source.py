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
