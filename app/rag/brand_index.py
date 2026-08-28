
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_INDEX = 1.0
# Brand price index: what a repair costs relative to the catalog baseline.

# app/rag/car_models.json gives each brand a multiplier. 
# reflecting parts and labour cost in the Colombian market. The
# pricing catalog holds one baseline price per pieza/defecto/severidad; the index
# scales it to the customer's actual vehicle.

@dataclass(frozen=True)
class Brand:
    name: str
    index: float
    models: tuple[str, ...]


@lru_cache
def _load() -> dict[str, Brand]:
    path = get_settings().car_models_path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        
        if not isinstance(raw, list):
            raise json.JSONDecodeError("Root is not a list", path, 0)
        
    except (OSError, json.JSONDecodeError) as exc:
        # Degrade to baseline pricing rather than failing the inspection.
        logger.error("Could not load brand index from %s: %s", path, exc)
        return {}

    brands: dict[str, Brand] = {}
    for item in raw:
        
        name = str(item.get("brand", "")).strip()
        
        if not name:
            continue
        
        brands[name.lower()] = Brand(
            name=name,
            index=float(item.get("index", DEFAULT_INDEX)),
            models=tuple(item.get("models", [])),
        )
        
    logger.info("Brand index loaded: %d brand(s).", len(brands))
    
    return brands


def get_brand(brand: str | None) -> Brand | None:
    
    if not brand:
        return None
    
    return _load().get(brand.strip().lower())


def brand_index(brand: str | None) -> float:
    """Multiplier for a brand. 1.0 when unknown or unspecified."""
    found = get_brand(brand)
    
    if brand and not found:
        # Degrade to baseline pricing rather than failing the inspection.
        logger.info("Unknown brand %r; using baseline pricing.", brand)
        
    return found.index if found else DEFAULT_INDEX


def apply_index(amount: int | None, index: float) -> int:
    """Scale a COP amount, rounded to a whole peso."""
    if not amount:
        return 0
    
    return int(round(amount * index))


def list_brands() -> list[dict]:
    """Brand + model catalog, for the frontend's select lists."""
    return [
        {"brand": b.name, 
         "index": b.index,
         "models": list(b.models)
         }
        for b in sorted(_load().values(), key=lambda x: x.name)
    ]


def models_for(brand: str) -> list[str]:
    
    found = get_brand(brand)
    
    return list(found.models) if found else []
