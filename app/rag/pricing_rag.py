"""
In-memory PricingTrie over AUTOPAIRS_CATALOG_PRICES.json.

Backs the [[query_pricing_batch]] tool. Unlike the compliance side this is exact
lookup, not semantic search: [[pieza -> tipo_defecto -> severidad]] is a dict
walk, so the English class names the vision models emit are the correct keys and
must not be translated.

Lookups degrade instead of failing, reporting how far they had to fall back:

    exact  -> the precise pieza/defecto/severidad node
    part+defect_generic  -> same pieza and defecto, nearest severidad
    part_generic   -> the `generic:<category>` node for that pieza
    not_found    -> nothing priced; the agent must not invent a figure

The distinction matters downstream: a quote built from  part_generic  is a
category estimate, not a price for that specific part, and should be presented
that way.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from app.core.config import get_settings
# PIEZA_CATEGORY lives in vocabulary.py: spatial matching needs the same
# part->category map for defect affinity.
from app.rag.brand_index import apply_index, brand_index, get_brand
from app.rag.vocabulary import PIEZA_CATEGORY, canonical_defect

logger = logging.getLogger(__name__)

FallbackLevel = Literal["exact", "part+defect_generic", "part_generic", "not_found"]

# leve < moderado < grave. Ordered so the nearest severity can be found when a
# pieza/defecto pair exists but not at the requested grade.
SEVERITY_ORDER: tuple[str, ...] = ("leve", "moderado", "grave")

# Business rule from the catalog's _schema_notes: these defects are always
# grave, which is why no leve/moderado rows exist for them. 
SEVERITY_FLOOR_GRAVE: frozenset[str] = frozenset({"glass_shatter", "lamp_broken"})


@dataclass(frozen=True)
class PricingEntry:
    service_name: str
    labor_hours: float
    labor_cost_cop: int
    materials_cost_cop: int
    parts_cost_cop: int | None
    total_cost_cop: int
    requires_replacement: bool
    pieza: str = ""
    tipo_defecto: str = ""
    severidad: str = ""
    category: str = ""
    is_generic_fallback: bool = False

    @classmethod
    def from_json(cls, raw: dict) -> "PricingEntry":
        return cls(
            service_name=raw["service_name"],
            labor_hours=float(raw.get("labor_hours") or 0),
            labor_cost_cop=int(raw.get("labor_cost_cop") or 0),
            materials_cost_cop=int(raw.get("materials_cost_cop") or 0),
            parts_cost_cop=raw.get("parts_cost_cop"),
            total_cost_cop=int(raw.get("total_cost_cop") or 0),
            requires_replacement=bool(raw.get("requires_replacement", False)),
            pieza=raw.get("pieza", ""),
            tipo_defecto=raw.get("tipo_defecto", ""),
            severidad=raw.get("severidad", ""),
            category=raw.get("category", ""),
            is_generic_fallback=bool(raw.get("is_generic_fallback", False)),
        )

    def to_dict(self) -> dict:
        """Serialisable shape for the tool result."""
        return {
            "service_name": self.service_name,
            "labor_hours": self.labor_hours,
            "labor_cost_cop": self.labor_cost_cop,
            "materials_cost_cop": self.materials_cost_cop,
            "parts_cost_cop": self.parts_cost_cop,
            "total_cost_cop": self.total_cost_cop,
            "requires_replacement": self.requires_replacement,
        }


@dataclass(frozen=True)
class LookupResult:
    entry: PricingEntry | None
    exact_match: bool
    fallback_level: FallbackLevel
    pieza: str = ""
    tipo_defecto: str = ""
    severidad: str = ""
    # Set when the severity floor rule overrode the requested grade.
    severidad_applied: str | None = None

    def to_dict(self) -> dict:
        
        d: dict = {
            "pieza": self.pieza,
            "tipo_defecto": self.tipo_defecto,
            "severidad": self.severidad,
            "exact_match": self.exact_match,
            "fallback_level": self.fallback_level,
            "entry": self.entry.to_dict() if self.entry else None,
        }
        if self.severidad_applied and self.severidad_applied != self.severidad:
            
            d["severidad_applied"] = self.severidad_applied
            
        return d


class PricingTrie:
    """Three-level trie: pieza -> tipo_defecto -> severidad -> PricingEntry.

    Keys are normalised on both insert and lookup (`.lower()` for defects, per
    the project-wide rule), so the catalog's `Cracks` matches a `cracks` query.
    """

    def __init__(self) -> None:
        self._root: dict[str, dict[str, dict[str, PricingEntry]]] = {}

 # build 
    def insert(
        self, pieza: str, 
        tipo_defecto: str, 
        severidad: str, 
        entry: PricingEntry
    ) -> None:
        
        p = pieza.strip().lower()
        d = canonical_defect(tipo_defecto)
        s = severidad.strip().lower()
        self._root.setdefault(p, {}).setdefault(d, {})[s] = entry

    # query  
    def lookup(self, 
               pieza: str, 
               tipo_defecto: str, 
               severidad: str
               ) -> LookupResult:
        
        p = pieza.strip().lower()
        d = canonical_defect(tipo_defecto)
        s_requested = severidad.strip().lower()

        # Apply the business floor before searching, so a mislabelled "leve"
        # glass_shatter still finds its (grave-only) node.
        s = "grave" if d in SEVERITY_FLOOR_GRAVE else s_requested
        applied = s if s != s_requested else None

        common = {
            "pieza": pieza,
            "tipo_defecto": tipo_defecto,
            "severidad": s_requested,
            "severidad_applied": applied,
        }

        #  exact
        node = self._root.get(p, {}).get(d)
        
        if node and s in node:
            
            return LookupResult(node[s], True, "exact", **common)

        #  same pieza and defecto, nearest severidad
        if node:
            
            nearest = self._nearest_severity(s, node)
            
            if nearest:
                
                return LookupResult(node[nearest], 
                                    False, 
                                    "part+defect_generic", 
                                    **common
                                    )

        #   the category's generic node
        category = PIEZA_CATEGORY.get(p) or self._category_of(p)
        
        if category:
            
            g_node = self._root.get(f"generic:{category}", {}).get(d)
            
            if g_node:
                
                pick = g_node.get(s) or (
                    
                    g_node[self._nearest_severity(s, g_node)]
                    if self._nearest_severity(s, g_node)
                    
                    else None
                )
                
                if pick:
                    
                    return LookupResult(pick, False, "part_generic", **common)

        return LookupResult(None, False, "not_found", **common)

    def lookup_batch(
        self, 
        queries: list[tuple[str, str, str]]
    ) -> list[LookupResult]:
        """One call per conversation with every detected defect."""
        return [self.lookup(p, d, s) for p, d, s in queries]

    def list_services_for_part(self, pieza: str) -> list[PricingEntry]:
        """Every priced service for a part -- the subtree enumeration."""
        p = pieza.strip().lower()
        
        return [
            entry
            for defect_node in self._root.get(p, {}).values()
            for entry in defect_node.values()
        ]

    #  internals  
    @staticmethod
    def _nearest_severity(target: str, 
                          node: dict[str, PricingEntry]
                          ) -> str | None:
        """
        Closest available grade to `target`.

        Ties break upward (grave over leve at equal distance): over-quoting is
        recoverable in conversation, under-quoting sets a false expectation.
        """
        if not node:
            
            return None
        
        if target not in SEVERITY_ORDER:
            
            return max(node, key=lambda s: SEVERITY_ORDER.index(s)
                       
                       if s in SEVERITY_ORDER else -1)
            
        t = SEVERITY_ORDER.index(target)
        
        return min(
            node,
            key=lambda s: (
                abs(SEVERITY_ORDER.index(s) - t) if s in SEVERITY_ORDER else 99,
                -(SEVERITY_ORDER.index(s) if s in SEVERITY_ORDER else 0),
            ),
        )

    def _category_of(self, pieza: str) -> str | None:
        """Category from any entry already stored for this pieza."""
        for defect_node in self._root.get(pieza, {}).values():
            
            for entry in defect_node.values():
                
                if entry.category:
                    
                    return entry.category
                
        return None

    def __len__(self) -> int:
        
        return sum(
            len(sev) for defects in self._root.values() for sev in defects.values()
        )

    @property
    def piezas(self) -> list[str]:
        return sorted(self._root)


def build_trie(catalog_path: Path | None = None) -> PricingTrie:
    """Load the catalog JSON into a trie."""
    path = catalog_path or get_settings().pricing_catalog_path
    
    with open(path, encoding="utf-8") as f:
        catalog = json.load(f)

    trie = PricingTrie()
    
    for raw in catalog["entries"]:
        
        trie.insert(
            raw["pieza"], raw["tipo_defecto"], 
            raw["severidad"],
            PricingEntry.from_json(raw),
        )
        
    logger.info("PricingTrie loaded: %d entries, %d piezas.", 
                len(trie), 
                len(trie.piezas))
    
    return trie


@lru_cache
def get_trie() -> PricingTrie:
    """Process-wide trie, built once at first use."""
    return build_trie()


# Spanish, agent-facing. Claude repeats these rather than inventing its own
# hedging, so the customer hears the same caveat every time.
FALLBACK_NOTE: dict[FallbackLevel, str] = {
    "exact": "Precio de catalogo para esta pieza, defecto y severidad.",
    "part+defect_generic": (
        "Precio de la severidad mas cercana disponible para esta pieza y defecto. "
        "Es una aproximacion."
    ),
    "part_generic": (
        "No hay precio especifico para esta pieza. Se usa el estimado generico de "
        "la categoria; el valor real puede variar."
    ),
    "not_found": (
        "No hay precio en el catalogo para esta combinacion. Requiere cotizacion "
        "manual del taller."
    ),
}

# I cannot rely Claude-Haiku to compute the totals, so  it s done here
def query_pricing_batch(
    defects: list[dict[str, str]], 
    *, 
    brand: str | None = None
    ) -> dict:
    """
    Tool-facing entry point. One call per conversation, all defects at once.

    Returns a summary object rather than a bare list, deliberately:

   Totals are computed here, [[$COP$]] not by the model.
    """
    seen: dict[tuple[str, str, str], int] = {}
    queries: list[tuple[str, str, str]] = []
    
    for d in defects:
        
        key = (
            d.get("pieza", ""),
            d.get("tipo_defecto", ""),
            d.get("severidad", ""),
        )
        
        if key not in seen:
            
            seen[key] = 0
            queries.append(key)
            #  here is where the actual priccing happens [Aritmetrics]
        seen[key] += 1

    results = get_trie().lookup_batch(queries)

    index = brand_index(brand)
    brand_info = get_brand(brand)

    items: list[dict] = []
    total = labor = materials = parts = 0
    n_exact = n_estimated = 0
    sin_precio: list[str] = []
    reemplazo: list[str] = []
    # COP  are high big numbers over six digits, so we use strings
    for r in results:
        
        qty = seen[(r.pieza, r.tipo_defecto, r.severidad)]
        item = r.to_dict()
        item["cantidad"] = qty
        item["precio_exacto"] = r.fallback_level == "exact"
        item["nota"] = FALLBACK_NOTE[r.fallback_level]

        if r.entry is None:
            
            sin_precio.append(f"{r.pieza}/{r.tipo_defecto}")
            
        else:
            e = r.entry
            # Scale each component so the breakdown still sums to the total.
            e_total = apply_index(e.total_cost_cop, index)
            e_labor = apply_index(e.labor_cost_cop, index)
            e_materials = apply_index(e.materials_cost_cop, index)
            e_parts = apply_index(e.parts_cost_cop, index)
            
            if item["entry"]:
                
                item["entry"].update({
                    "labor_cost_cop": e_labor,
                    "materials_cost_cop": e_materials,
                    "parts_cost_cop": e_parts,
                    "total_cost_cop": e_total,
                })
                
            item["subtotal_cop"] = e_total * qty
            
            total += e_total * qty
            labor += e_labor * qty
            materials += e_materials * qty
            parts += e_parts * qty
            
            if r.fallback_level == "exact":
                
                n_exact += 1
                
            else:
                n_estimated += 1
                
            if e.requires_replacement:
                
                reemplazo.append(f"{r.pieza}/{r.tipo_defecto}")

        items.append(item)

    return {
        
        "items": items,
        "resumen": {
            "total_cop": total,
            "subtotal_mano_obra_cop": labor,
            "subtotal_materiales_cop": materials,
            "subtotal_repuestos_cop": parts,
            "items_con_precio_exacto": n_exact,
            "items_estimados": n_estimated,
            "items_sin_precio": sin_precio,
            "requieren_reemplazo": reemplazo,
            "moneda": "COP",
            "marca": brand_info.name if brand_info else (brand or None),
            "indice_marca": index,
        },
        "instrucciones": (
            "total_cop ya esta calculado: usalo tal cual, no vuelvas a sumar. "
            "Los precios YA incluyen el ajuste por marca del vehiculo "
            "(indice_marca): no lo apliques otra vez ni hagas multiplicaciones. "
            "Si items_estimados > 0, aclara que parte del valor es estimado. "
            "Si items_sin_precio no esta vacio, esos defectos NO estan incluidos "
            "en el total y requieren cotizacion del taller: menciona cuales."
        ),
    }
