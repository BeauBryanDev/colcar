"""Class policy: normalisation, RTM routing, affinity, query wording."""

from __future__ import annotations

from app.rag.vocabulary import (
    POSITIVE_FINDING_CLASSES,
    build_query_text,
    is_affine,
    is_defect_class,
    is_ignored_part,
    is_rtm_relevant,
    normalize_defect,
    severity_display,
)


def test_normalize_defect_lowercases_without_singularising():
    assert normalize_defect("  Cracks ") == "cracks"
    assert normalize_defect("Flat spots") == "flat spots"
    ## crack and cracks are distinct catalog types.
    assert normalize_defect("Crack") != normalize_defect("Cracks")


def test_cosmetic_damage_is_out_of_rtm_scope():
    assert is_rtm_relevant("back_left_door", "scratch") is False
    assert is_rtm_relevant("front_bumper", "dent") is False
    ## Cosmetic damage on an inspected part is still cosmetic.
    assert is_rtm_relevant("front_left_light", "scratch") is False


def test_every_light_class_is_in_rtm_scope():
    lights = (
        "front_light", "front_left_light", "front_right_light",
        "back_light", "back_left_light", "back_right_light",
    )
    assert all(is_rtm_relevant(light, "crack") for light in lights)


def test_floor_defects_are_in_scope_on_any_part():
    assert is_rtm_relevant("back_left_door", "lamp_broken") is True
    assert is_rtm_relevant("unknown", "glass_shatter") is True
    assert is_rtm_relevant("hood", "pitting") is True


def test_affinity_rejects_implausible_parts():
    assert is_affine("lamp_broken", "front_left_light") is True
    assert is_affine("lamp_broken", "back_left_door") is False
    assert is_affine("glass_shatter", "front_glass") is True
    assert is_affine("glass_shatter", "hood") is False
    ## Unconstrained defects go anywhere.
    assert is_affine("scratch", "hood") is True


def test_query_text_uses_the_standard_wording():
    cracks = build_query_text("tire", "Cracks")
    assert "bandas laterales" in cracks
    assert "grieta" not in cracks
    assert "corrosion" in build_query_text("hood", "pitting")
    assert "grave" in build_query_text("front_glass", "glass_shatter", "grave")


def test_object_is_dropped_and_good_is_a_positive_finding():
    assert is_ignored_part("object") is True
    assert is_ignored_part("hood") is False
    assert "good" in POSITIVE_FINDING_CLASSES
    assert is_defect_class("Good") is False
    assert is_defect_class("Bulge") is True


def test_severity_display_maps_internal_keys():
    assert severity_display("leve") == "Bajo"
    assert severity_display("moderado") == "Medio"
    assert severity_display("grave") == "Grave"
