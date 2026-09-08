
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.db import mongo

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


#  sources::same rule as pricing_rag: Mongo is the source of truth, the
#  JSON file is the seed and the fallback, both yield the same dict shape.

# Which source the loaded index came from, for /health and the startup log.
_source: str = "none"


def _brands_from_file(path: Path | None = None) -> list[dict]:
    
    path = path or get_settings().car_models_path
    raw = json.loads(path.read_text(encoding="utf-8"))
    
    if not isinstance(raw, list):
        
        raise json.JSONDecodeError("Root is not a list", str(path), 0)
    
    return raw


def _brands_from_mongo() -> list[dict]:
    """Every brand document. Raises PyMongoError when unreachable."""
    s = get_settings()
    
    coll = mongo.get_db(s)[s.brands_collection]
    
    return list(coll.find({}, {"_id": False}))


def loaded_source() -> str:
    """'mongo', 'json', or 'none' when neither source could be read."""
    _load()
    return _source


@lru_cache
def _load() -> dict[str, Brand]:
    global _source
    raw: list[dict] | None = None

    if mongo.is_configured():
        try:
            raw = _brands_from_mongo()
            if not raw:
                raise ValueError("collection is empty -- run scripts/seed_catalog.py")
            
            _source = "mongo"
            
        except Exception as exc:  # noqa: BLE001 - network or data, degrade either way
            logger.error(
                "Brand index: MongoDB unavailable (%s); falling back to JSON", exc
            )
            raw = None

    if raw is None:
        try:
            raw = _brands_from_file()
            _source = "json"
        except (OSError, json.JSONDecodeError) as exc:
            # Degrade to baseline pricing rather than failing the inspection.
            logger.error("Could not load brand index from JSON: %s", exc)
            _source = "none"
            
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
        
    logger.info("Brand index loaded from %s: %d brand(s).", _source, len(brands))
    
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
