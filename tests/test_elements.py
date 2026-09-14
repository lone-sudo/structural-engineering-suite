import pytest
from elements.slab import TwoWaySlab
from elements.beam import ContinuousBeam
from elements.column import ColumnDesign
from elements.footing import PadFooting


def test_slab_keeps_gk_and_qk_separate():
    s = TwoWaySlab(4, 5, code="BS8110")
    r = s.design_panel()
    assert r["gk_slab_kpa"] > 0
    assert r["qk_slab_kpa"] == 2.0
    assert r["w_beam_long_gk_kN_m"] > 0
    assert r["w_beam_long_qk_kN_m"] > 0


def test_beam_now_supports_genuinely_unequal_spans():
    # This restriction was intentionally removed: the beam engine now uses
    # a real matrix analysis (core/beam_analysis.py) instead of an
    # equal-spans-only coefficient table. Unequal spans must be accepted
    # and produce genuinely different moments per span, not identical
    # values silently copied from a single representative span.
    b = ContinuousBeam([4.0, 6.0, 5.0], gk_slab=10, qk_slab=5, code="BS8110")
    r = b.design_beam()
    assert r["num_spans"] == 3
    lengths = [s["length_m"] for s in r["spans_detail"]]
    assert lengths == [4.0, 6.0, 5.0]
    moments = [s["M_span_kNm"] for s in r["spans_detail"]]
    assert len(set(moments)) == 3, "unequal spans must produce distinct span moments, not a copied value"


def test_beam_supports_independent_depth_and_width_per_span():
    b = ContinuousBeam([5.0, 5.0], b_w=[200.0, 300.0], h_overall=[400.0, 600.0], gk_slab=10, qk_slab=5, code="BS8110")
    r = b.design_beam()
    depths = [s["h_overall"] for s in r["spans_detail"]]
    widths = [s["b_w"] for s in r["spans_detail"]]
    assert depths == [400.0, 600.0]
    assert widths == [200.0, 300.0]


def test_beam_span_count_is_not_capped_at_three():
    b = ContinuousBeam([4.0] * 6, gk_slab=10, qk_slab=5, code="BS8110")
    r = b.design_beam()
    assert r["num_spans"] == 6
    assert len(r["spans_detail"]) == 6


def test_ec2_beam_shear_is_now_designed():
    # EC2 shear (variable strut inclination method) is implemented; the suite
    # must produce a real PASS/FAIL, not silently claim NOT CHECKED anymore.
    b = ContinuousBeam([5, 5], code="Eurocode 2")
    r = b.design_beam()
    assert r["shear_status"] in {"PASS", "FAIL"}


def test_bs8110_footing_punching_shear_is_now_screened():
    f = PadFooting(N_service=500, N_ultimate=700, col_cx=300, col_cy=300, q_allowable=150, code="BS8110")
    L, B, _ = f.size_plan_dimensions()
    res = f.design_reinforcement_and_shear(L, B)
    checks = {c["name"]: c["status"] for c in res["audit"]["checks"]}
    assert checks["Punching shear (perimeter 1.5d screening)"] in {"PASS", "FAIL"}


def test_beam_deflection_screening_is_now_checked_for_bs8110():
    b = ContinuousBeam([5, 5], code="BS8110")
    r = b.design_beam()
    assert r["deflection_status"] in {"PASS", "FAIL"}
    assert r["allowable_span_d"] is not None


def test_column_has_real_symmetric_arrangement():
    c = ColumnDesign(
        b=300, h=300, num_floors=2,
        Gk_beam_per_floor=50, Qk_beam_per_floor=25,
        code="Eurocode 2"
    )
    r = c.design_column()
    assert r["main_rebar"]["bars"] >= 4
    assert r["main_rebar"]["As_prov"] >= r["Asc_req_mm2"]


def test_bs8110_short_column_min_eccentricity_does_not_false_fail():
    # A short BS8110 column with no applied moment must not be double-penalised:
    # the Cl. 3.8.4.3 axial formula already covers minimum eccentricity.
    c = ColumnDesign(
        b=300, h=300, clear_height=3000, num_floors=4,
        Gk_beam_per_floor=60, Qk_beam_per_floor=30,
        f_cu=30, f_y=460, code="BS8110"
    )
    r = c.design_column()
    assert r["is_short"] is True
    assert r["moment_status"] == "PASS"


def test_bs8110_slender_column_with_real_moment_can_fail_and_recover():
    undersized = ColumnDesign(
        b=200, h=200, clear_height=5000, num_floors=3,
        Gk_beam_per_floor=40, Qk_beam_per_floor=20, Mx_applied=15.0,
        f_cu=25, f_y=460, code="BS8110"
    )
    r_small = undersized.design_column()
    assert r_small["is_short"] is False
    assert r_small["Madd_x_kNm"] > 0
    assert r_small["moment_status"] == "FAIL"

    adequate = ColumnDesign(
        b=350, h=350, clear_height=5000, num_floors=3,
        Gk_beam_per_floor=40, Qk_beam_per_floor=20, Mx_applied=15.0,
        f_cu=25, f_y=460, code="BS8110"
    )
    r_big = adequate.design_column()
    assert r_big["moment_status"] == "PASS"


def test_column_rejects_negative_applied_moment():
    with pytest.raises(ValueError):
        ColumnDesign(b=300, h=300, num_floors=2, Gk_beam_per_floor=50, Qk_beam_per_floor=25, Mx_applied=-5.0)


def test_column_service_load_never_exceeds_ultimate_for_ordinary_dead_load_dominant_case():
    # Regression test: N_service previously double-counted the beam's Gk
    # (via a reused `gk_total` variable meaning different things in the
    # legacy vs. normal load paths), so an entirely ordinary dead-load-
    # dominant column — ordinary in real buildings, not an edge case —
    # could come back with a service load HIGHER than its own ultimate
    # load. That broke the Pad Footing Design 🔗 link, which rejects
    # N_ultimate < N_service as physically nonsensical.
    c = ColumnDesign(b=300, h=300, num_floors=3, Gk_beam_per_floor=60, Qk_beam_per_floor=20, f_cu=25, f_y=460, code="BS8110")
    r = c.design_column()
    assert r["N_serv_to_footing_kN"] < r["N_ult_total_kN"]

    # Hand-calculated expected service load: (60+20)*3 beam service load,
    # plus the column's own self-weight (0.3*0.3*3*24 per floor) — the beam's
    # Gk must appear in this total exactly once, not twice.
    expected_service = (60 + 20) * 3 + (0.3 * 0.3 * 3 * 24) * 3
    assert abs(r["N_serv_to_footing_kN"] - expected_service) < 0.5

    # The legacy (pre-set ultimate-beam-reaction) load path was already
    # correct before this fix and must remain so.
    c2 = ColumnDesign(b=300, h=300, num_floors=3, N_beam_per_floor=100, f_cu=25, f_y=460, code="BS8110")
    r2 = c2.design_column()
    assert r2["N_serv_to_footing_kN"] < r2["N_ult_total_kN"]


def test_footing_checks_service_bearing():
    f = PadFooting(300, 450, 300, 300, 150, code="Eurocode 2")
    L, B, q = f.size_plan_dimensions()
    r = f.design_reinforcement_and_shear(L, B)
    assert r["q_service_kpa"] <= 150
    assert "Punching shear" in [x["name"] for x in r["audit"]["checks"]]


def test_ec2_column_axial_resistance_is_reported():
    c = ColumnDesign(
        b=300, h=300, clear_height=3000, num_floors=2,
        Gk_beam_per_floor=50, Qk_beam_per_floor=25,
        f_cu=25, f_y=460, code="Eurocode 2"
    )
    r = c.design_column()
    # The sidebar/constructor now collects the real EC2 cylinder strength
    # (fck) directly — f_cu=25 here means fck=25 MPa, not a cube strength
    # requiring a 0.8 conversion (that approximation was removed).
    # fcd = 0.85*25/1.5; fyd = 460/1.15. The selected 4Y12 arrangement
    # provides about 452.4 mm².
    expected_nrd = (300 * 300 * (0.85 * 25 / 1.5) + 452.4 * (460 / 1.15)) / 1000
    assert abs(r["N_rd_kN"] - expected_nrd) < 0.2
    assert r["axial_resistance_status"] == "PASS"
    assert r["N_ult_total_kN"] == 227.5


def test_bs8110_column_uses_eq38_resistance():
    c = ColumnDesign(
        b=300, h=300, clear_height=3000, num_floors=2,
        Gk_beam_per_floor=50, Qk_beam_per_floor=25,
        f_cu=25, f_y=460, code="BS8110"
    )
    r = c.design_column()
    expected_nrd = (0.40 * 25 * 300 * 300 + r["main_rebar"]["As_prov"] * 0.75 * 460) / 1000
    assert abs(r["N_rd_kN"] - expected_nrd) < 0.2
    assert r["axial_resistance_status"] == "PASS"


def test_two_way_slab_supports_all_bs8110_table_3_14_panel_types():
    panel_types = [
        "Interior Panel",
        "One Short Edge Discontinuous",
        "One Long Edge Discontinuous",
        "Two Adjacent Edges Discontinuous",
        "Two Short Edges Discontinuous",
        "Two Long Edges Discontinuous",
        "Three Edges Discontinuous (One Long Edge Continuous)",
        "Three Edges Discontinuous (One Short Edge Continuous)",
        "Four Edges Discontinuous",
    ]
    for panel in panel_types:
        r = TwoWaySlab(4.0, 5.0, panel_type=panel, code="BS8110").design_panel()
        assert r["analysis_method"] == "BS 8110 Table 3.14 coefficient method"
        assert r["Msx_pos"] >= 0
        assert r["Msy_pos"] >= 0


def test_four_edges_discontinuous_has_no_negative_support_moment():
    r = TwoWaySlab(4.0, 5.0, panel_type="Four Edges Discontinuous", code="BS8110").design_panel()
    assert r["Msx_neg"] == 0
    assert r["Msy_neg"] == 0


def test_slab_design_load_is_independent_of_edge_condition():
    loads = []
    panels = list(TwoWaySlab.BS_COEFFS)
    for panel in panels:
        loads.append(TwoWaySlab(4.0, 5.0, panel_type=panel, code="BS8110").design_panel()["n_ult_kpa"])
    assert len(set(loads)) == 1


def test_bs_slab_minimum_steel_uses_gross_depth():
    r = TwoWaySlab(4.0, 5.0, h_slab=150, f_y=460, code="BS8110").design_panel()
    expected_min = 0.0013 * 1000 * 150
    assert r["rebar_sx"]["As_req"] >= expected_min


def test_two_span_beam_uses_exact_equal_span_reaction():
    b = ContinuousBeam([5.0, 5.0], gk_slab=10, qk_slab=5, code="BS8110")
    r = b.design_beam()
    w = r["w_ult_kN_m"]
    assert abs(r["M_support_kNm"] - w * 25 / 8) < 1e-6
    assert abs(r["V_support_kN"] - 5 * w * 5 / 8) < 1e-6
    gk_total = r["spans_detail"][0]["gk_total_kN_m"]
    assert abs(r["reaction_gk_to_column_kN"] - 1.25 * gk_total * 5) < 1e-6


def test_two_way_slab_edge_condition_changes_moments():
    interior = TwoWaySlab(4.0, 5.0, panel_type="Interior Panel", code="BS8110").design_panel()
    four_edges = TwoWaySlab(4.0, 5.0, panel_type="Four Edges Discontinuous", code="BS8110").design_panel()
    assert interior["n_ult_kpa"] == four_edges["n_ult_kpa"]
    assert interior["Msx_pos"] != four_edges["Msx_pos"]
    assert interior["Msy_pos"] != four_edges["Msy_pos"]


def test_one_way_slab_returns_design_actions():
    from elements.slab import OneWaySlab
    r = OneWaySlab(5.0, h_slab=150, code="BS8110").design()
    assert r["M_u_kNm_per_m"] > 0
    assert r["V_u_kN_per_m"] > 0
    assert r["rebar"]["As_prov"] >= r["As_req_mm2_m"]
