"""Tests for the Phase-1 design-depth features added in v30:
strain-compatibility column interaction, EC2 second-order columns, EC2 crack
width, and EC2 anchorage/lap lengths.
"""
import pytest

from core.detailing import ec2_anchorage, ec2_lap
from core.rebar import RebarSelector
from core.section_analysis import (
    BarLayer,
    axial_capacity,
    biaxial_utilization,
    interaction_curve,
    moment_capacity,
)
from core.serviceability import cracked_section_stress, ec2_crack_width
from core.standards import BS8110, design_flexure_T
from elements.beam import ContinuousBeam
from elements.column import ColumnDesign
from elements.slab import OneWaySlab


def test_section_analysis_pure_axial_capacity_matches_code_value():
    layers = [BarLayer(226.2, 39), BarLayer(226.2, 261)]
    N0 = axial_capacity(300, 300, layers, 25, 460, "BS8110")
    curve = interaction_curve(300, 300, layers, 25, 460, "BS8110")
    # The curve should reach the pure-axial capacity at large x.
    assert max(p.N_kN for p in curve) == pytest.approx(N0, rel=1e-6)


def test_section_analysis_matches_the_flexure_formula_for_a_singly_reinforced_section():
    # Cross-check the strain-compatibility solver against the independent
    # BS 8110 flexure formula used elsewhere in the suite.
    M_cap = moment_capacity(0.0, 300, 450, [BarLayer(1200, 450)], 30, 460, "BS8110")
    As_req = BS8110.design_flexure(M_cap, 300, 450, 30, 460, min_steel_h=500)["As_req"]
    assert As_req == pytest.approx(1200.0, rel=0.02)


def test_section_analysis_pure_moment_capacity_is_physical():
    layers = [BarLayer(226.2, 39), BarLayer(226.2, 261)]
    M0 = moment_capacity(0, 300, 300, layers, 25, 460, "BS8110")
    # 2Y12 tension at ~400 MPa over a ~240 mm lever gives roughly 20 kNm.
    assert 15.0 < M0 < 30.0


def test_biaxial_utilization_increases_with_applied_moment():
    pos = RebarSelector.column_bar_positions(4, 300, 300, 25, 8, 12)
    bars = [(x, y, 113.1) for x, y in pos]
    low = biaxial_utilization(400, 5, 5, 300, 300, bars, 25, 460, "Eurocode 2")
    high = biaxial_utilization(400, 25, 25, 300, 300, bars, 25, 460, "Eurocode 2")
    assert high["utilization"] > low["utilization"]


def test_ec2_slender_column_now_includes_nominal_curvature_moment():
    c = ColumnDesign(
        b=200, h=200, clear_height=3000, num_floors=2,
        Gk_beam_per_floor=100, Qk_beam_per_floor=50,
        f_cu=25, f_y=460, code="Eurocode 2",
    )
    res = c.design_column()
    assert res["is_short"] is False
    assert res["second_order_status"] == "INCLUDED (EC2)"
    assert res["M2_x_kNm"] > 0
    statuses = {c["name"]: c["status"] for c in res["audit"]["checks"]}
    assert statuses["Slenderness — second-order moment"] == "WARNING"


def test_cracked_section_stress_increases_with_moment():
    low = cracked_section_stress(50, 250, 450, 800, 25, "Eurocode 2")
    high = cracked_section_stress(100, 250, 450, 800, 25, "Eurocode 2")
    assert high["sigma_s"] > low["sigma_s"]
    # For a linear cracked section the neutral-axis depth depends on the
    # section/steel, not on the magnitude of M.
    assert high["x_mm"] == pytest.approx(low["x_mm"])


def test_ec2_crack_width_for_a_typical_beam_is_reported():
    beam = ContinuousBeam(
        [5.0, 5.0], b_w=250, h_overall=500, gk_slab=12, qk_slab=6,
        wall_height=0, code="Eurocode 2",
    )
    res = beam.design_beam()
    span = res["spans_detail"][0]
    assert span["wk_span_mm"] is not None
    assert span["wk_span_mm"] > 0
    assert span["crack_span_status"] in {"PASS", "FAIL"}
    assert res["crack_status"] in {"PASS", "FAIL"}


def test_bs8110_crack_width_is_honestly_not_checked():
    beam = ContinuousBeam(
        [5.0, 5.0], b_w=250, h_overall=500, gk_slab=12, qk_slab=6,
        wall_height=0, code="BS8110",
    )
    res = beam.design_beam()
    assert res["crack_status"] == "NOT CHECKED"
    assert res["spans_detail"][0]["wk_span_mm"] is None


def test_ec2_crack_width_increases_with_service_moment():
    low = ec2_crack_width(50, 250, 500, 450, 800, 16, 35, 25, 500)
    high = ec2_crack_width(100, 250, 500, 450, 800, 16, 35, 25, 500)
    assert high["wk_mm"] > low["wk_mm"]


def test_ec2_anchorage_and_lap_lengths_increase_with_bar_diameter():
    lbd16 = ec2_anchorage(16, 25, 500)["lbd_mm"]
    lbd20 = ec2_anchorage(20, 25, 500)["lbd_mm"]
    assert lbd20 > lbd16 > 0
    lap = ec2_lap(16, 25, 500)["l0_mm"]
    assert lap >= 15 * 16
    assert lap >= 200


def test_ec2_bbs_beam_bottom_length_includes_anchorage():
    from pipeline.building import BuildingModel

    model = BuildingModel(4, 5, num_storeys=2, code="Eurocode 2")
    results = model.run_full_design()
    rows = model.bbs_rows(results)
    beam_row = next(r for r in rows if r["Bar Mark"] == "B01-1")
    span = results["beam"]["spans_detail"][0]
    assert beam_row["Cut Length (m)"] > float(span["length_m"])


def test_t_beam_sagging_design_uses_the_flange():
    t = design_flexure_T(
        "BS8110", M=300.0, b_eff=1000.0, b_w=250.0, h_f=150.0,
        d=450.0, h=500.0, f_c=30.0, f_y=460.0,
    )
    rect = BS8110.design_flexure(300.0, 250, 450, 30, 460, min_steel_h=500)
    assert "T-beam" in t["section_type"]
    assert t["As_req"] < rect["As_req"]
    assert t["x"] > 0


def test_t_beam_web_neutral_axis_branch_is_solved_correctly():
    # Regression for a sign error in the T-section quadratic: at this
    # moment the neutral axis must be below the 150 mm flange.
    t = design_flexure_T(
        "BS8110", M=800.0, b_eff=1000.0, b_w=250.0, h_f=150.0,
        d=450.0, h=500.0, f_c=30.0, f_y=460.0,
    )
    assert "web" in t["section_type"]
    assert 150.0 < t["x"] < 450.0
    assert t["As_req"] > 4000.0


def test_continuous_beam_accepts_a_t_beam_flange():
    t_beam = ContinuousBeam(
        [5.0], b_w=250, h_overall=500, gk_slab=20, qk_slab=10,
        wall_height=0, code="BS8110",
        flange_width=1000.0, flange_thickness=150.0,
    ).design_beam()
    rect_beam = ContinuousBeam(
        [5.0], b_w=250, h_overall=500, gk_slab=20, qk_slab=10,
        wall_height=0, code="BS8110",
    ).design_beam()
    assert "T-beam" in t_beam["spans_detail"][0]["section_type"]
    assert t_beam["spans_detail"][0]["flange_width_mm"] == 1000.0
    assert t_beam["span_bars"]["As_prov"] <= rect_beam["span_bars"]["As_prov"]


def test_one_way_slab_ec2_reports_crack_width():
    res = OneWaySlab(4.0, h_slab=175, code="Eurocode 2").design()
    assert res["crack_status"] in {"PASS", "FAIL", "NOT CHECKED"}
    assert res["M_qp_kNm_per_m"] > 0
