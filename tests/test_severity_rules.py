"""Severity grading: bands, denominators, legal floor, tyre type rules."""

from __future__ import annotations

from app.vision.severity_rules import (
    grade_from_ratio,
    severity_for_image_relative,
    severity_for_match,
    severity_for_part_relative,
    severity_for_tyre,
)


def test_bands_are_half_open():
    assert grade_from_ratio(0.0999, leve_max=0.10, moderado_max=0.25) == "leve"
    assert grade_from_ratio(0.10, leve_max=0.10, moderado_max=0.25) == "moderado"
    assert grade_from_ratio(0.25, leve_max=0.10, moderado_max=0.25) == "grave"


def test_matched_defect_divides_by_part_area():
    result = severity_for_part_relative("dent", 150.0, 1000.0)
    assert result.severidad == "moderado"
    assert result.basis_kind == "part_relative"
    assert result.basis == "area_ratio:0.1500"


def test_legal_floor_overrides_a_tiny_area():
    result = severity_for_part_relative("glass_shatter", 1.0, 1000.0)
    assert result.severidad == "grave"
    assert result.basis_kind == "legal_floor"
    assert "glass_shatter" in result.basis


def test_zero_part_area_degrades_to_leve():
    result = severity_for_part_relative("dent", 500.0, 0.0)
    assert result.severidad == "leve"
    assert result.ratio == 0.0


def test_unmatched_defects_use_the_higher_image_bands():
    assert severity_for_image_relative("dent", 150.0, 1000.0).severidad == "leve"
    assert severity_for_image_relative("dent", 300.0, 1000.0).severidad == "moderado"
    assert severity_for_image_relative("dent", 500.0, 1000.0).severidad == "grave"


def test_tyre_defects_are_graded_by_type_not_area():
    bulge = severity_for_tyre("Bulge", 5.0, 1000.0)
    pitting = severity_for_tyre("Pitting", 800.0, 1000.0)
    assert bulge.severidad == "grave"
    assert bulge.basis_kind == "tyre_type_rule"
    assert pitting.severidad == "leve"


def test_extensive_tyre_wear_escalates_to_grave():
    minor = severity_for_tyre("Flat spots", 50.0, 1000.0)
    extensive = severity_for_tyre("Flat spots", 627.0, 1000.0)
    assert minor.severidad == "moderado"
    assert "flat spots:type" in minor.basis
    assert extensive.severidad == "grave"
    assert "flat spots:extent" in extensive.basis


def test_match_picks_the_denominator_and_payload_carries_both_labels(
    make_detection, make_match
):
    defect = make_detection("dent", (0, 0, 20, 20), with_mask=True)
    part = make_detection("hood", (0, 0, 40, 40), with_mask=True)

    matched = severity_for_match(make_match(defect, part), image_area_px=160_000.0)
    unmatched = severity_for_match(make_match(defect, None), image_area_px=160_000.0)

    assert matched.basis_kind == "part_relative"
    assert unmatched.basis_kind == "image_relative"
    payload = matched.to_payload()
    assert payload["severidad"] == matched.severidad
    assert payload["severidad_display"] in ("Bajo", "Medio", "Grave")
