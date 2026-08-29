"""
Semantic search over the Colombian RTM compliance corpus.

Backs the [[query_compliance]] tool exposed to Claude. Retrieval mirrors the
search() helper in ml/Compliance_RAG.ipynb: embed the query with bge-m3, then
query_points against `compliance_normativa`.

Corpus (412 chunks, see CLAUDE.md):
  resolucion_3768_2013 (binding)  - split per articulo, vigente/derogado
  ntc_5375, ntc_5385   (binding)   - narrative sections + A/B defect rows
  concepto_2025...     (NOT binding) - advisory legal opinion

[[binding]] and [[estado]] matter legally: a non-binding concepto or a derogated
article must never be presented to the customer as a cause of RTM rejection.
Defaults here exclude both; the agent-facing tool relies on that.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core.config import get_settings
from app.rag.qdrant_client import embed_text, get_client
from app.rag.vocabulary import build_query_text, is_rtm_relevant

logger = logging.getLogger(__name__)

Severidad = Literal["leve", "moderado", "grave"]

# NTC 5375 grades each table defect A or B. B is the heavier grade (rechazo),
# so a severe finding is matched against B rows first.
_SEVERITY_TO_CLASS: dict[str, str] = {
    "leve": "A",
    "moderado": "B",
    "grave": "B",
}

# Chunk text is long; trim before it reaches the model's context.
_MAX_TEXT_CHARS = 900


def _build_filter(
    *,
    only_binding: bool,
    only_vigente: bool,
    severidad: str | None,
    ) -> Filter | None:
    """
    Compose the payload filter.

    [[estado]] is only set on resolucion chunks -- NTC chunks leave it null hence so
    filtering on estado == "vigente"` would silently drop the entire NTC corpus.
    Instead the derogated ones are excluded by [[must_not]], which leaves nulls in.
    """
    must: list[FieldCondition] = []
    must_not: list[FieldCondition] = []

    if only_binding:
        
        must.append(FieldCondition(key="binding", match=MatchValue(value=True)))

    if only_vigente:
        
        must_not.append(
            FieldCondition(
                key="estado", match=MatchValue(value="historico_derogado")
            )
        )

    if severidad:
        
        rejection_class = _SEVERITY_TO_CLASS.get(severidad.lower())
        
        if rejection_class:
            
            must.append(
                FieldCondition(
                    key="severidad", match=MatchValue(value=rejection_class)
                )
            )

    if not must and not must_not:
        
        return None
    
    return Filter(must=must or None, must_not=must_not or None)


def _format_hit(point: Any) -> dict[str, Any]:
    """Flatten a scored point into the shape handed back to Claude."""
    p: dict[str, Any] = point.payload or {}
    text: str = (p.get("text") or "").strip()
    truncated = len(text) > _MAX_TEXT_CHARS

    return {
        "score": round(point.score, 4),
        "documento": p.get("document_name"),
        "document_id": p.get("document_id"),
        "tipo_documento": p.get("document_type"),
        "vinculante": p.get("binding"),
        "estado": p.get("estado"),
        "articulo": p.get("articulo_numero"),
        "seccion": p.get("seccion"),
        # A / B grade from the NTC 5375 defect tables; null on narrative chunks.
        "clase_rechazo": p.get("severidad"),
        "tipo_vehiculo": p.get("tipo_vehiculo"),
        "modificado_por": p.get("modificado_por"),
        "texto": text[:_MAX_TEXT_CHARS] + ("..." if truncated else ""),
    }


def query_compliance(
    pieza: str,
    tipo_defecto: str,
    severidad: str | None = None,
    *,
    top_k: int | None = None,
    only_binding: bool = True,
    only_vigente: bool = True,
    filter_by_severity: bool = False,
    force: bool = False,
    ) -> list[dict[str, Any]]:
    """
    Retrieve regulation passages relevant to one detected defect.

    Args:
        pieza: part name from the vision pipeline, e.g. "front_bumper".
        tipo_defecto: defect class, e.g. "scratch", "Cracks".
        severidad: leve | moderado | grave. Included in the query text; only
            used as a hard filter when `filter_by_severity` is set, since the
            A/B grade exists on defect-table rows and would exclude the
            narrative articles that usually carry the best context.
        only_binding: drop the advisory concepto juridico.
        only_vigente: drop articles superseded by a later resolution.
        force: search even when the defect is outside NTC 5375's scope.
            Diagnostics only -- results will be misleading.

    Returns hits ordered by descending cosine similarity, or [] when the defect
    is one the standard does not cover.
    """
    s = get_settings()
    limit = top_k or s.compliance_top_k

    # Route before searching. The corpus has no cosmetic-damage content, and its
    # near-misses score in the same band as genuine hits, so a defect the
    # standard does not cover must not reach the encoder at all  
    if not force and not is_rtm_relevant(pieza, tipo_defecto):
        logger.debug(
            "query_compliance skipped: %s/%s is outside NTC 5375 scope",
            pieza, tipo_defecto,
        )
        return []

    # The corpus is Spanish, so the English vision labels are translated first.
    query_text = build_query_text(pieza, tipo_defecto, severidad)
    # this is all the reason the big vocabuary.py file exists
    query_filter = _build_filter(
        
        only_binding=only_binding,
        only_vigente=only_vigente,
        severidad=severidad if filter_by_severity else None,
    )

    response = get_client().query_points(
        
        collection_name=s.qdrant_collection,
        query=embed_text(query_text),
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )

    hits = [_format_hit(pt) for pt in response.points]
    
    logger.debug(
        "query_compliance(%r, %r, %r) -> %d hits", 
        pieza, 
        tipo_defecto, 
        severidad, 
        len(hits)
    )
    return hits


def query_compliance_batch(
    defects: list[dict[str, str]],
    *,
    top_k: int | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
    """
    Run [[query_compliance]] for several defects.

    Keyed "pieza|tipo_defecto" so the agent can line results up with the defect
    list it was given. Duplicate defects are searched once.
    """
    results: dict[str, list[dict[str, Any]]] = {}
    
    for defect in defects:
        
        pieza = defect.get("pieza", "")
        tipo = defect.get("tipo_defecto", "")
        key = f"{pieza}|{tipo}"
        
        if key in results:
            
            continue
        
        results[key] = query_compliance(
            
            pieza, 
            tipo, 
            defect.get("severidad"), 
            top_k=top_k
        )
        
    return results


def search(query: str, 
           top_k: int = 5, 
           only_binding: bool = False
           ) -> list[dict[str, Any]]:
    """Free-text search -- the notebook's `search()`, for debugging."""
    s = get_settings()
    
    response = get_client().query_points(
        
        collection_name=s.qdrant_collection,
        query=embed_text(query),
        query_filter=_build_filter(
            only_binding=only_binding, 
            only_vigente=False, 
            severidad=None
        ),
        limit=top_k,
        with_payload=True,
    )
    
    return [_format_hit(pt) for pt in response.points]
