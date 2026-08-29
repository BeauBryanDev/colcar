"""
English vision-class -> Spanish RTM vocabulary.

The vision models and the PricingTrie both key off English class names, and they
stay that way: trie lookups are exact-match, so translating them would break
retrieval of prices.

"""

from __future__ import annotations

#  Piezas (car parts) 
PIEZA_ES: dict[str, str] = {
    # Bumpers
    "front_bumper": "parachoques delantero",
    "back_bumper": "parachoques trasero",
    # Doors
    "front_door": "puerta delantera",
    "front_left_door": "puerta delantera izquierda",
    "front_right_door": "puerta delantera derecha",
    "back_door": "puerta trasera", 
    "back_left_door": "puerta trasera izquierda",
    "back_right_door": "puerta trasera derecha",
    # Glass
    "front_glass": "vidrio panoramico delantero",
    "back_glass": "vidrio trasero",
    # Lights
    "front_light": "farola delantera",
    "front_left_light": "luz delantera izquierda",
    "front_right_light": "luz delantera derecha",
    "back_light": "luces traseras",
    "back_left_light": "luz trasera izquierda",
    "back_right_light": "luz trasera derecha",
    # Mirrors
    "left_mirror": "espejo izquierdo",
    "right_mirror": "espejo derecho",
    # Body
    "hood": "capo",
    "trunk": "baul o cajuela",
    "tailgate": "porton trasero",
    # Wheels
    "tire": "llanta",
    "wheel": "llanta rueda rin",
    # Generic fallback nodes from the pricing catalog
    "generic:body_panel": "carroceria",
    "generic:glass": "vidrios",
    "generic:light": "luces",
    "generic:mirror": "espejo retrovisor",
    "generic:tire": "llanta",
}

# Tipos de defecto  
DEFECTO_ES: dict[str, str] = {
    "scratch": "rayonazo rayon en la pintura",
    "dent": "abolladura",
    "crack": "grieta",
    # `Cracks` is the tyre model's class. Phrased as NTC 5375 words sidewall
    # damage, which is "rotura", not "grieta" -- the bare "grietas" retrieved a
    "cracks": "despegue o rotura en las bandas laterales",
    "glass_shatter": "vidrio roto",
    # Deflated tyre  
    "tire_flat": "llanta desinflada sin presion de aire",
    "lamp_broken": "lampara rota luz en mal estado",
    "puncture": "pinchado",
    # Matches the corpus wording directly: "Corrosion en carroceria. Tipo B".
    "pitting": "corrosion",
    # Kept distinct from `dent` ("abolladura") on purpose: a tyre sidewall
    # bulge and a body dent are different defects, and identical Spanish would
    # make them retrieve identically.
    "bulge": "abultamiento lateral de la llanta",
    # Worn flat patch on the tread (tyre model), not a deflated tyre.
    "flat_spot": "aplanamiento y desgaste plano de la banda de rodadura",
    "flat_spots": "aplanamiento y desgaste plano de la banda de rodadura",
}

# Severity is already Spanish; included so query text reads naturally.
SEVERIDAD_ES: dict[str, str] = {
    "leve": "leve",
    "moderado": "moderado",
    "grave": "grave",
}

# Parts model catch-all. Not a real panel: leaving it in would let a defect
# match to "object" instead of the actual bumper it sits on.
IGNORED_PART_CLASSES: frozenset[str] = frozenset({"object"})

# The tyre model classifies healthy tyres as `Good`. It is a *positive*
# finding, not a defect: pricing it would invent a repair and a legal warning
# for a sound tyre. Dropped from the defect list, but reported separately so
# the agent can tell the customer the tyres were inspected and are fine.
POSITIVE_FINDING_CLASSES: frozenset[str] = frozenset({"good"})

# Cross-model defect aliases, when two models name the same physical problem
# differently. Empty for now.
#
# NOT an alias: the surface model's `tire_flat` (a deflated tyre  a pressure
# problem) and the tyre model's `Flat spots` (a worn flat patch where the tread
# has lost its texture, usually from locked-wheel braking  a wear problem).
DEFECT_ALIASES: dict[str, str] = {}


# Part -> catalog category. Owned here rather than in pricing_rag because two
# unrelated consumers need it: the PricingTrie's `generic:<category>` fallback,
# and spatial matching's defect/part affinity.
PIEZA_CATEGORY: dict[str, str] = {
    "front_bumper": "body_panel",
    "back_bumper": "body_panel",
    "front_door": "body_panel",
    "front_left_door": "body_panel",
    "front_right_door": "body_panel",
    "back_door": "body_panel",
    "back_left_door": "body_panel",
    "back_right_door": "body_panel",
    "hood": "body_panel",
    "trunk": "body_panel",
    "tailgate": "body_panel",
    "front_glass": "glass",
    "back_glass": "glass",
    "front_light": "light",
    "front_left_light": "light",
    "front_right_light": "light",
    "back_light": "light",
    "back_left_light": "light",
    "back_right_light": "light",
    "left_mirror": "mirror",
    "right_mirror": "mirror",
    "tire": "tire",
    "wheel": "wheel_rim",
}

# Defects that can only occur on one kind of part. A broken lamp is a lamp on a
# light; shattered glass is glass. Where a defect is listed here, parts outside
# its categories are not eligible at all.
DEFECT_PART_AFFINITY: dict[str, frozenset[str]] = {
    "lamp_broken": frozenset({"light"}),
    "glass_shatter": frozenset({"glass"}),
}

# Defects that are always [[GRAVE]], whatever their measured area. Driving with a
# broken lamp or shattered glass is illegal, so a small crack in a windscreen is
# not a small problem. Mirrors the catalog's `_schema_notes.severity_floor_rule`
# (those defects have no leve/moderado rows).
ALWAYS_GRAVE_DEFECTS: frozenset[str] = frozenset({"glass_shatter", "lamp_broken"})

# Internal severity keys are Spanish already and match the pricing catalog's
# `severidad` field -- do not rename them, the trie is keyed on these. The
# frontend shows the display labels instead.
SEVERITY_DISPLAY_ES: dict[str, str] = {
    "leve": "Bajo",
    "moderado": "Medio",
    "grave": "Grave",
}


def severity_display(severidad: str) -> str:
    """Frontend label for an internal severity key."""
    return SEVERITY_DISPLAY_ES.get(severidad.strip().lower(), severidad)


def is_always_grave(tipo_defecto: str) -> bool:
    return canonical_defect(tipo_defecto) in ALWAYS_GRAVE_DEFECTS


# Tyre severity is driven by defect *type*, not by area.
#
# Measured on real tyre photos, genuine defects occupy 0.3%-6.5% of the frame:
# a sidewall bulge at 0.800 confidence covered 6.5% and graded `leve` under an
# area rule, which would call a blowout risk minor. NTC 5375 grades sidewall
# rupture Tipo B irrespective of size, so type is the honest signal -- the same
# reasoning as the glass/lamp legal floor.
#
# `Cracks` and `Flat spots` escalate to `grave` once extensive .
TYRE_SEVERITY_BASE: dict[str, str] = {
    "bulge": "grave",     # sidewall separation, imminent blowout risk
    "puncture": "moderado",  # frequently repairable
    "cracks": "moderado",    # grave when extensive
    "flat spots": "moderado",  # grave when extensive
    "pitting": "leve",       # surface corrosion
}

# Types whose grade may rise with extent; everything else keeps its base grade.
TYRE_ESCALATABLE: frozenset[str] = frozenset({"cracks", "flat spots"})


def tyre_base_severity(tipo_defecto: str) -> str | None:
    """Base grade for a tyre defect class, or None if unknown."""
    return TYRE_SEVERITY_BASE.get(canonical_defect(tipo_defecto))


def tyre_can_escalate(tipo_defecto: str) -> bool:
    return canonical_defect(tipo_defecto) in TYRE_ESCALATABLE


def part_category(pieza: str) -> str | None:
    """Catalog category for a part class, or None if unknown."""
    return PIEZA_CATEGORY.get(normalize_key(pieza))


def affinity_categories(tipo_defecto: str) -> frozenset[str] | None:
    """Part categories this defect may occur on, or None if unconstrained."""
    return DEFECT_PART_AFFINITY.get(canonical_defect(tipo_defecto))


def is_affine(tipo_defecto: str, pieza: str) -> bool:
    """Whether this defect can plausibly sit on this part."""
    allowed = affinity_categories(tipo_defecto)
    if allowed is None:
        return True
    
    category = part_category(pieza)
    
    return category in allowed if category else False


def canonical_defect(tipo_defecto: str) -> str:
    """Normalised defect label with cross-model aliases resolved."""
    normalized = normalize_defect(tipo_defecto)
    
    return DEFECT_ALIASES.get(normalized.replace(" ", "_"), normalized)


def is_defect_class(tipo_defecto: str) -> bool:
    """False for `Good` -- a positive finding, not something to price."""
    return normalize_defect(tipo_defecto) not in POSITIVE_FINDING_CLASSES


def is_ignored_part(pieza: str) -> bool:
    """True for the parts model's `object` catch-all."""
    return normalize_key(pieza) in IGNORED_PART_CLASSES


#   RTM coverage routing  
# NTC 5375 is a roadworthiness standard: it covers what makes a vehicle unsafe
# or illegal to drive, not cosmetic condition. Nothing in the corpus addresses a
# scratched bumper or a dented door, so a search for one returns the least-bad
# match  so a similarity threshold cannot
# separate them. The split has to be made before searching.

# Parts the standard inspects, whatever the defect.
# NOTE: every light class the parts model emits must be listed. The front
# left/right variants were missing, so a broken headlight matched to
# `front_left_light` was routed as cosmetic and reported "no es causal de
# rechazo" RTM -- the opposite of the truth.
_RTM_PIEZAS: frozenset[str] = frozenset({
    "tire", "wheel", "generic:tire",
    "front_glass", "back_glass", "generic:glass",
    "front_light", "front_left_light", "front_right_light",
    "back_light", "back_left_light", "back_right_light",
    "generic:light",
    "left_mirror", "right_mirror", "generic:mirror",
})

# Defects that matter anywhere on the vehicle, including body panels.
# Corrosion is explicitly graded by the standard ("Corrosion en carroceria.
# Clasificacion: Tipo B"), so it stays in scope even on cosmetic parts.
_RTM_DEFECTS_ANY_PIEZA: frozenset[str] = frozenset({
    "pitting", "lamp_broken", "glass_shatter",
})

# Cosmetic defects, out of scope unless the part itself is inspected
# (a cracked windscreen is a visibility defect; a scratched bumper is not).
_COSMETIC_DEFECTS: frozenset[str] = frozenset({"scratch", "dent"})
# RTM does not care about these, so they are not in the Trie.

def is_rtm_relevant(pieza: str, tipo_defecto: str) -> bool:
    """Whether NTC 5375 plausibly has something to say about this defect."""
    p = normalize_key(pieza)
    d = normalize_key(tipo_defecto)

    if d in _RTM_DEFECTS_ANY_PIEZA:
        return True
    
    if p in _RTM_PIEZAS:
        # Cosmetic damage to an inspected part is still cosmetic: a scratched
        # headlight lens is not a lighting defect.
        return d not in _COSMETIC_DEFECTS
    
    return False


def normalize_defect(raw: str) -> str:
    """
    Canonical form for a defect label: lowercase, everywhere.

    The vision models are inconsistent -- the tyre model emits `Cracks`,
    `Bulge`, `Flat spots` while the surface model emits `scratch`, `dent` --
    and the pricing catalog stores them exactly as emitted. Lowercasing on both
    the write and read side is the project-wide rule, so apply this when
    loading the PricingTrie *and* when looking up in it.
    """
    return raw.strip().lower()


def normalize_key(raw: str) -> str:
    """Lookup key for the tables in this module.

    Same lowercasing, plus space/hyphen -> underscore so `Flat spots` and
    `flat_spot` both resolve here. Module-local: the trie uses
    `normalize_defect` alone.
    """
    return normalize_defect(raw).replace(" ", "_").replace("-", "_")


def pieza_es(pieza: str) -> str:
    """Spanish part name, falling back to the raw label if unmapped."""
    return PIEZA_ES.get(normalize_key(pieza), pieza.replace("_", " "))


def defecto_es(tipo_defecto: str) -> str:
    """Spanish defect name, falling back to the raw label if unmapped."""
    return DEFECTO_ES.get(normalize_key(tipo_defecto), tipo_defecto.replace("_", " "))


def build_query_text(pieza: str, 
                     tipo_defecto: str, 
                     severidad: str | None = None
                     ) -> str:
    """Compose the Spanish string handed to the embedder."""
    parts = [pieza_es(pieza), defecto_es(tipo_defecto)]
    
    if severidad:
        
        parts.append(SEVERIDAD_ES.get(severidad.lower(), severidad))
        
    return " ".join(p for p in parts if p)
