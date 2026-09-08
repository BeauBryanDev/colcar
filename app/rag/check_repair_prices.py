
from __future__ import annotations

import logging
from typing import Any

from app.rag.brand_index import apply_index, brand_index, get_brand
from app.rag.pricing_rag import (
    FALLBACK_NOTE,
    SEVERITY_ORDER,
    LookupResult,
    PricingEntry,
    get_trie,
)
from app.rag.vocabulary import (
    PIEZA_CATEGORY,
    canonical_defect,
    defecto_es,
    normalize_key,
    pieza_es,
)

logger = logging.getLogger(__name__)

# What the model may ask about. Vision part classes (PIEZA_CATEGORY) reach
# prices through their own rows or their category's generic node; the
# generic nodes themselves are not offered as piezas.
KNOWN_PIEZAS: tuple[str, ...] = tuple(sorted(PIEZA_CATEGORY))

# Price lookups for whatever the *user* asks about -- not what vision found.

# Nothing is aadded to this list, but the tool result says so.

def known_defects() -> list[str]:
    """Every defect type priced anywhere in the catalog."""
    trie = get_trie()
    return sorted({
        d for p in trie.piezas for d in trie._root[p]  # noqa: SLF001
    })


def _priced_entry(entry: PricingEntry, 
                  index: float
                  ) -> dict[str, Any]:
    """Entry dict with the brand index applied to every component."""
    d = entry.to_dict()
    d.update({
        "labor_cost_cop": apply_index(entry.labor_cost_cop, index),
        "materials_cost_cop": apply_index(entry.materials_cost_cop, index),
        "parts_cost_cop": apply_index(entry.parts_cost_cop, index),
        "total_cost_cop": apply_index(entry.total_cost_cop, index),
    })
    return d


def _row_from_lookup(r: LookupResult, 
                     index: float
                     ) -> dict[str, Any]:
    # The tool result says so.
    row = r.to_dict()
    row["pieza_es"] = pieza_es(r.pieza)
    row["tipo_defecto_es"] = defecto_es(r.tipo_defecto)
    row["precio_exacto"] = r.fallback_level == "exact"
    row["nota"] = FALLBACK_NOTE[r.fallback_level]
    
    if r.entry is not None:
        
        row["entry"] = _priced_entry(r.entry, index)
        
    return row


def _row_from_entry(entry: PricingEntry, 
                    pieza: str, 
                    index: float
                    ) -> dict[str, Any]:
    
    generic = entry.pieza.startswith("generic:")
    
    level = "part_generic" if generic else "exact"
    
    return {
        "pieza": pieza,
        "pieza_es": pieza_es(pieza),
        "tipo_defecto": entry.tipo_defecto,
        "tipo_defecto_es": defecto_es(entry.tipo_defecto),
        "severidad": entry.severidad,
        "exact_match": not generic,
        "fallback_level": level,
        "precio_exacto": not generic,
        "nota": FALLBACK_NOTE[level],
        "entry": _priced_entry(entry, index),
    }


def _services_for(pieza: str, 
                  index: float
                  ) -> list[dict[str, Any]]:
    """Every priced service for a part, via its category node if it has none."""
    trie = get_trie()
    
    entries = trie.list_services_for_part(pieza)
    
    if not entries:
        
        category = PIEZA_CATEGORY.get(pieza)
        
        if category:
            
            entries = trie.list_services_for_part(f"generic:{category}")
            
    order = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    
    entries = sorted(
        entries, 
        key=lambda e: (e.tipo_defecto, order.get(e.severidad, 99))
    )
    
    return [_row_from_entry(e, pieza, index) for e in entries]


def check_repair_prices(
    consultas: list[dict[str, str]], 
    *, 
    brand: str | None = None
) -> dict[str, Any]:
    """Tool-facing entry point. 
    See the module docstring for the three levels."""
    index = brand_index(brand)
    brand_info = get_brand(brand)
    trie = get_trie()

    out: list[dict[str, Any]] = []
    
    for q in consultas:
        
        pieza = normalize_key(str(q.get("pieza", "")))
        defecto = str(q.get("tipo_defecto", "") or "").strip()
        severidad = str(q.get("severidad", "") or "").strip().lower()

        item: dict[str, Any] = {
            "consulta": {
                "pieza": pieza or None,
                "tipo_defecto": defecto or None,
                "severidad": severidad or None,
            },
            "resultados": [],
        }

        if not pieza or pieza not in PIEZA_CATEGORY:
            
            item["nota"] = (
                "Pieza no reconocida. Usa exactamente uno de los nombres en "
                "'piezas_validas'."
            )
            
        elif defecto and severidad:
            
            item["resultados"] = [
                _row_from_lookup(trie.lookup(pieza, defecto, severidad), index)
            ]
            
        elif defecto:
            
            item["resultados"] = [
                _row_from_lookup(trie.lookup(pieza, defecto, s), 
                                 index
                                 )
                for s in SEVERITY_ORDER 
            ]
            
            if canonical_defect(defecto) in {"glass_shatter", "lamp_broken"}:
                # The floor collapses all three to the grave row: say it once.
                item["resultados"] = item["resultados"][-1:]
                item["nota"] = (
                    "Este defecto siempre se cotiza como grave (regla del catalogo)."
                )
                
        else:
            item["resultados"] = _services_for(pieza, index)
            
            if not item["resultados"]:
                
                item["nota"] = "No hay servicios en el catalogo para esta pieza."

        if item["resultados"] and all(
            r.get("entry") is None for r in item["resultados"]
        ):
            item["nota"] = (
                "Sin precio en el catalogo para esta combinacion: requiere "
                "cotizacion manual del taller."
            )
            
        out.append(item)

    logger.info("check_repair_prices: %d consulta(s), brand=%s", len(out), brand)
    
    return {
        
        "consultas": out,
        "resumen": {
            "moneda": "COP",
            "marca": brand_info.name if brand_info else (brand or None),
            "indice_marca": index,
        },
        "piezas_validas": list(KNOWN_PIEZAS),
        "tipos_defecto_validos": known_defects(),
        "instrucciones": (  # Agent talks to the user in Spanish, so the instructions are too.
            "Son precios de referencia del catalogo para lo que el usuario "
            "pregunto, NO una cotizacion de la inspeccion: no los sumes ni los "
            "mezcles con el total de query_pricing_batch. Los precios YA "
            "incluyen el ajuste por marca (indice_marca): no lo apliques otra "
            "vez. Si precio_exacto es false, aclara que es un estimado de la "
            "categoria. Si entry es null, di que no hay precio en el catalogo "
            "y que el taller debe cotizarlo; nunca inventes una cifra."
        ),
    }
