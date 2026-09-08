
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import CarSpecsUnavailableError

# Engine specifications from API Ninjas /v1/cars. 
# The free tier is limited to 50 requests per day, 
# so the agent must degrade gracefully when it fails.

logger = logging.getLogger(__name__)

# API field -> Spanish label the agent can quote. Order is display order.
SPEC_FIELDS: dict[str, str] = {
    "make": "marca",
    "model": "modelo",
    "year": "anio",
    "class": "clase",
    "displacement": "cilindraje_litros",
    "cylinders": "cilindros",
    "fuel_type": "combustible",
    "drive": "traccion",
    "transmission": "transmision",
    "horsepower": "caballos_fuerza",
    "torque": "torque",
    "city_mpg": "consumo_ciudad_mpg",
    "highway_mpg": "consumo_carretera_mpg",
    "combination_mpg": "consumo_mixto_mpg",
}


_TRANSMISSION = {"a": "automatica", "m": "manual"}
_DRIVE = {"fwd": "delantera", "rwd": "trasera", "awd": "integral", "4wd": "4x4"}


def _clean(value: Any) -> Any:
    """
    Premium-only fields arrive as a *string* on the free tier
    ("this field is for premium subscribers only"). Map that to None so the
    agent reports "no disponible" instead of quoting the upsell."""
    if isinstance(value, str) and "premium" in value.lower():
        return None
    
    return value


def _shape(raw: dict[str, Any]) -> dict[str, Any]:
    """Project one API record onto the Spanish keys, keeping absent as None."""
    out = {label: _clean(raw.get(key)) for key, label in SPEC_FIELDS.items()}
    t = out.get("transmision")
    
    if isinstance(t, str):
        out["transmision"] = _TRANSMISSION.get(t.lower(), t)
        
    d = out.get("traccion")
    
    if isinstance(d, str):
        
        out["traccion"] = _DRIVE.get(d.lower(), d)
        
    return out


def get_car_specs(
    make: str,
    model: str | None = None, 
    year: int | str | None = None,
    *, 
    limit: int = 1,
) -> list[dict[str, Any]]:
    """
    Query API Ninjas for a vehicle. Returns [] when nothing matches.

    Raises CarSpecsUnavailableError when the key is missing or the request
    fails, so the caller can degrade.
    """
    settings = get_settings()
    
    if settings.api_ninja_key is None:
        # The agent can still run without the key, but it will never get specs.
        raise CarSpecsUnavailableError(
            detail="La consulta de fichas tecnicas no esta configurada.",
            log_message="API_NINJA_KEY is not set",
        )

    # `limit` is NOT sent: API Ninjas rejects it with 400 on the free tier
    # ("The limit parameter is for premium users only"). Truncate client-side.
    params: dict[str, Any] = {"make": make.strip()}
    
    if model:
        params["model"] = str(model).strip()
        
    if year:
        params["year"] = str(year).strip()

    # TODO: THIS API-NINJA IS VERY LIMITED. 
    #  I MIGHT NEED TO USE ANOTHER WHICH A BIGGER FREE TIER.

    try:
        response = httpx.get(
            settings.api_ninja_cars_url,
            params=params,
            headers={"X-Api-Key": settings.api_ninja_key.get_secret_value()},
            timeout=settings.api_ninja_timeout,
        )
        response.raise_for_status()
        data = response.json()
        
    except httpx.HTTPStatusError as exc:
        
        raise CarSpecsUnavailableError(
            log_message=(
                f"API Ninjas returned {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            )
        ) from exc
        
    except (httpx.HTTPError, ValueError) as exc:
        
        raise CarSpecsUnavailableError(
            log_message=f"API Ninjas request failed: {exc}"
        ) from exc

    if not isinstance(data, list):
        
        raise CarSpecsUnavailableError(
            log_message=f"API Ninjas returned unexpected payload: {data!r:.200}"
        )

    records = [_shape(r) for r in data if isinstance(r, dict)][:limit]
    
    logger.info(
        "car_specs: %s %s %s -> %d record(s)", make, model or "-", year or "-",
        len(records),
    )
    return records
