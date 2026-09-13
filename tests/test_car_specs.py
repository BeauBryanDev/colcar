"""Engine-specs tool: context-only identity, degradation, payload shaping.

Offline: `httpx.get` is monkeypatched with a fake response, and the conftest
`no_network` fixture would fail any real request by name.
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.agent import tools_iml
from app.agent.tools_iml import execute_tool
from app.agent.tools_schema import QUERY_CAR_SPECS
from app.core.exceptions import CarSpecsUnavailableError
from app.rag import car_specs

_RECORD = {
    "make": "toyota", "model": "corolla", "year": 2020, "class": "compact car",
    "displacement": 1.8, "cylinders": 4, "fuel_type": "gas", "drive": "fwd",
    "transmission": "a", "city_mpg": 30, "highway_mpg": 38,
    "combination_mpg": "this field is for premium subscribers only",
}


@pytest.fixture
def with_key(settings, monkeypatch):
    monkeypatch.setattr(settings, "api_ninja_key", SecretStr("test-ninja-key"))
    return settings


@pytest.fixture
def fake_http(monkeypatch):
    """Record the outgoing request and answer with a canned body."""
    calls: list[dict] = []

    def install(body, status=200):
        def fake_get(url, *, params=None, headers=None, timeout=None):
            calls.append({"url": url, "params": params, "headers": headers})
            req = httpx.Request("GET", url)
            return httpx.Response(status, json=body, request=req)

        monkeypatch.setattr(car_specs.httpx, "get", fake_get)
        return calls

    return install


def test_schema_has_no_arguments():
    # The vehicle is a server-side fact; the model must not be able to
    # override it, exactly like the brand multiplier.
    assert QUERY_CAR_SPECS["input_schema"]["properties"] == {}


def test_identity_comes_from_context_not_tool_input(with_key, fake_http):
    calls = fake_http([_RECORD])
    result = execute_tool(
        "query_car_specs",
        {"make": "BMW", "model": "X5", "year": 2010},
        context={"brand": "Toyota", "model": "Corolla", "year": 2020},
    )
    assert calls[0]["params"]["make"] == "Toyota"
    assert calls[0]["params"]["model"] == "Corolla"
    assert calls[0]["params"]["year"] == "2020"
    assert calls[0]["headers"]["X-Api-Key"] == "test-ninja-key"
    assert result["vehiculo"] == {"marca": "Toyota", "modelo": "Corolla", "anio": 2020}

    spec = result["especificaciones"][0]
    assert spec["cilindraje_litros"] == 1.8
    assert spec["cilindros"] == 4
    assert spec["transmision"] == "automatica"
    assert spec["traccion"] == "delantera"
    ## Premium-only fields are absent (or an upsell string) on the free tier:
    ## kept as None, never dropped and never quoted.
    assert "caballos_fuerza" in spec and spec["caballos_fuerza"] is None
    assert spec["consumo_mixto_mpg"] is None
    assert spec["consumo_ciudad_mpg"] == 30


def test_no_vehicle_in_session_does_not_call_the_api(with_key, fake_http):
    calls = fake_http([_RECORD])
    result = tools_iml.run_query_car_specs({"make": "Toyota"}, context={})
    assert calls == []
    assert result["vehiculo"] is None
    assert result["especificaciones"] == []


def test_empty_match_is_explicit(with_key, fake_http):
    fake_http([])
    result = tools_iml.run_query_car_specs({}, context={"brand": "Zoyte"})
    assert result["especificaciones"] == []
    assert "No se encontro" in result["instrucciones"]


def test_missing_key_degrades(settings, monkeypatch):
    monkeypatch.setattr(settings, "api_ninja_key", None)
    with pytest.raises(CarSpecsUnavailableError):
        tools_iml.run_query_car_specs({}, context={"brand": "Toyota"})


def test_http_error_degrades(with_key, fake_http):
    fake_http({"error": "quota"}, status=429)
    with pytest.raises(CarSpecsUnavailableError):
        tools_iml.run_query_car_specs({}, context={"brand": "Toyota"})


def test_key_is_redacted_from_logs(with_key):
    from app.core.logging import _secret_values

    assert "test-ninja-key" in _secret_values(with_key)
