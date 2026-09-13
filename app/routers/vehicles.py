
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.rag.brand_index import list_brands

# Vehicle catalog for the frontend's brand / model / year selects.
# The brand determines the price index in ./app/rag/brand_index.py,

router = APIRouter(prefix="/vehicles", tags=["vehicles"])

# TODO: Oldest model year offered in the select. Colombian RTM applies from the
# vehicle's second year, so there is no value in going back further than the
# fleet realistically in service.
_OLDEST_YEAR = 1990


@router.get("/brands")
async def brands() -> dict:
    """Brands, their models, and the valid year range.

    One call fills all three selects: `brands[].brand`, `brands[].models`,
    and `years`. `index` is included for transparency, not for the SPA to
    apply -- all pricing arithmetic happens server-side.
    """
    current = datetime.now(timezone.utc).year
    
    return {
        "brands": list_brands(),
        "years": list(range(current + 1, _OLDEST_YEAR - 1, -1)),
    }
