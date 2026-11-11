"""Regression tests for the engineering-hardening review (v29).

Each test here protects a specific, previously-unsafe or previously-missing
behaviour. They are intentionally written as hand-checkable assertions, not
just snapshots of current output.
"""
import pytest

from core.beam_analysis import SpanInput, SpanLoadInput, analyze_continuous_beam, envelope_analysis
from core.rebar import RebarSelector
from core.standards import BS8110, Eurocode2
from elements.beam import ContinuousBeam
from elements.column import ColumnDesign
from elements.footing import PadFooting
from elements.stair import StairFlight


def test_pattern_loading_uses_10gk_not_14gk_on_unloaded_spans():
    """BS 8110 3.2.1.2.2(b) requires 1.0Gk on unloaded spans.

    Using 1.4Gk raises the hogging moments at the supports of the adjacent
    unloaded spans, which REDUCES the sagging moment in the fully loaded
    span. That is unconservative, so the correct envelope must be higher.
    """
    L, gk, qk = 6.0, 6.0, 8.0
    spans = [
        SpanLoadInput(length_m=L, I_relative=1.0, gk_kn_m=gk, qk_kn_m=qk, gamma_g=1.4, gamma_q=1.6)
        for _ in range(3)
    ]
    env = envelope_analysis(spans)

    full = 1.4 * gk + 1.6 * qk
    old_style = analyze_continuous_beam([
        SpanInput(length_m=L, I_relative=1.0, w_ult_kn_m=w)
        for w in (full, 1.4 * gk, full)
    ])
    assert env[0].M_span_max_kNm > old_style[0].M_span_max_kNm + 1.0


def test_bs8110_minimum_steel_depends_on_fy():
    mild = BS8110.design_flexure(0.0, 1000, 150, 25, 250, min_steel_h=200)
    high = BS8110.design_flexure(0.0, 1000, 150, 25, 460, min_steel_h=200)
    assert abs(mild["As_min"] - 0.0024 * 1000 * 200) < 1e-6
    assert abs(high["As_min"] - 0.0013 * 1000 * 200) < 1e-6
    assert mild["As_min"] > high["As_min"]


def test_ec2_biaxial_exponent_uses_all_three_anchor_points():
    assert Eurocode2.biaxial_exponent(0.05) == 1.0
    assert Eurocode2.biaxial_exponent(0.1) == 1.0
    assert abs(Eurocode2.biaxial_exponent(0.4) - 1.25) < 1e-9
    assert abs(Eurocode2.biaxial_exponent(0.7) - 1.5) < 1e-9
    assert abs(Eurocode2.biaxial_exponent(0.85) - 1.75) < 1e-9
    assert Eurocode2.biaxial_exponent(1.0) == 2.0
    assert Eurocode2.biaxial_exponent(1.2) == 2.0


def test_ec2_span_depth_limit_is_within_expected_range():
    out = Eurocode2.span_depth_limit(
        f_ck=25.0, As_req=300.0, As_prov=314.0, b=1000.0, d=120.0, K=1.0
    )
    # For rho ~ 0.25% and fck=25 the EC2 expression gives roughly 40.
    assert 15.0 < out["allowable_span_d"] < 60.0
    assert out["rho"] == pytest.approx(300.0 / (1000.0 * 120.0))


def test_slab_spacing_never_under_provides_steel():
    for As_req in (0.0, 200.0, 400.0, 800.0, 1200.0, 2000.0, 4000.0):
        sel = RebarSelector.select_slab_spacing(As_req, bar_dia=10, max_spacing=250)
        assert sel["passes_area"] is True, (As_req, sel)
        assert sel["As_prov"] + 1e-9 >= As_req
        assert sel["spacing"] >= 75


def test_slab_spacing_prefers_placeable_spacing_over_75mm_congestion():
    sel = RebarSelector.select_slab_spacing(800.0, bar_dia=10, max_spacing=250)
    assert sel["spacing"] >= 100
    assert sel["bar_diameter"] >= 12


def test_beam_bars_must_fit_the_beam_width_in_one_layer():
    # A 200 mm beam cannot physically take 2 kNm of steel in one layer of
    # 16-25 mm bars; the selector must refuse rather than draw it.
    opts = RebarSelector.select_beam_bars(2000.0, b_w=200, cover=25, link_dia=8)
    assert opts == []

    # A smaller demand still produces a single-layer arrangement with a
    # geometry field that the caller can check.
    opts2 = RebarSelector.select_beam_bars(900.0, b_w=200, cover=25, link_dia=8)
    assert opts2
    assert all(o["layers"] == 1 for o in opts2)
    assert all(o["max_bars_per_layer"] >= 2 for o in opts2)


def test_footing_one_way_shear_audit_cannot_show_pass_with_demand_over_capacity():
    f = PadFooting(N_service=2000, N_ultimate=2800, col_cx=300, col_cy=300,
                   q_allowable=150, h_overall=300, code="BS8110")
    L, B, _ = f.size_plan_dimensions()
    res = f.design_reinforcement_and_shear(L, B)
    checks = {c["name"]: c for c in res["audit"]["checks"]}
    one_way = checks["One-way shear (unreinforced)"]
    assert one_way["status"] == "FAIL"
    assert one_way["demand"] > one_way["capacity"]


def test_footing_enforces_buried_pad_cover():
    f = PadFooting(N_service=500, N_ultimate=750, col_cx=300, col_cy=300,
                   q_allowable=150, h_overall=450, cover=25, code="BS8110")
    assert f.cover >= 50.0
    L, B, _ = f.size_plan_dimensions()
    res = f.design_reinforcement_and_shear(L, B)
    assert res["cover_mm"] >= 50.0


def test_stair_result_includes_a_real_audit_and_shear_check():
    res = StairFlight(code="BS8110").design_stair()
    names = [c["name"] for c in res["audit"]["checks"]]
    assert "Flexural reinforcement" in names
    assert "Shear (unreinforced)" in names
    assert "Deflection (span/depth screening)" in names
    assert res["audit"]["overall_status"] in {"PASS", "FAIL", "NOT CHECKED", "WARNING"}


def test_ec2_slender_column_is_not_classified_as_short():
    c = ColumnDesign(b=200, h=200, clear_height=3000, num_floors=2,
                     Gk_beam_per_floor=100, Qk_beam_per_floor=50,
                     f_cu=25, f_y=460, code="Eurocode 2")
    res = c.design_column()
    assert res["is_short"] is False
    assert res["slenderness_x"] > res["lambda_lim"]
    statuses = {c["name"]: c["status"] for c in res["audit"]["checks"]}
    assert statuses["Slenderness — second-order moment"] == "NOT CHECKED"


def test_column_bar_layouts_return_the_requested_bar_count():
    for n in (4, 6, 8, 10, 12):
        pts = RebarSelector.column_bar_positions(n, b=400, h=400, cover=25, link_dia=8, dia=16)
        assert len(pts) == n
        for x, y in pts:
            assert 25 < x < 375
            assert 25 < y < 375


def test_pdf_reader_ignores_unlabelled_four_digit_numbers():
    import pymupdf
    from pipeline.pdf_reader import PDFPlanReader

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "TEL 0712 345 678   DATE 2024   DRAWING NO 4001")
    parsed = PDFPlanReader.extract_plan_parameters(doc.tobytes())
    assert parsed["spans_detected"] is False
    assert parsed["spans_m"] is None


def test_dxf_reader_derives_spans_from_a_real_grid_not_line_lengths():
    import io
    import ezdxf
    from pipeline.dxf_reader import CADReader

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    # Vertical grid lines at x = 0, 4, 9; horizontal at y = 0, 5, 11.
    for x in (0, 4, 9):
        msp.add_line((x, 0), (x, 11))
    for y in (0, 5, 11):
        msp.add_line((0, y), (9, y))
    # A stray 7 m architectural line that is not part of the grid.
    msp.add_line((0, 0), (7, 0))

    buf = io.StringIO()
    doc.write(buf)
    parsed = CADReader.parse_dxf_stream(buf.getvalue().encode("utf-8"))

    assert parsed["x_spans"] == [4.0, 5.0]
    assert parsed["y_spans"] == [5.0, 6.0]
    assert parsed["detected_spans"] == [4.0, 5.0]


def test_ec2_report_labels_concrete_as_fck_not_fcu():
    from core.reporter import StructuralReporter

    res = ContinuousBeam([5, 5], code="Eurocode 2").design_beam()
    html = StructuralReporter.generate_single_element_report(
        "Beam Design", res, code="Eurocode 2", f_cu=25, f_y=500
    )
    assert "fck = 25" in html
    assert "fcu = 25" not in html


def test_project_json_round_trip_keeps_numbers_as_numbers():
    import json
    from core.persistence import json_safe

    res = ContinuousBeam([5.0], code="BS8110").design_beam()
    payload = json_safe({"beam": res})
    text = json.dumps(payload)
    loaded = json.loads(text)
    assert isinstance(loaded["beam"]["M_span_kNm"], float)
    assert isinstance(loaded["beam"]["w_ult_kN_m"], float)
    assert isinstance(loaded["beam"]["spans_detail"][0]["M_span_kNm"], float)


def test_dxf_column_section_draws_all_twelve_bars():
    import io
    import ezdxf
    from core.dxf_export import generate_column_dxf

    fake = {
        "main_rebar": {"bar_diameter": 16, "bar_count": 12, "description": "12Y16", "As_prov": 2413},
        "link_schedule": "Y8 ties @ 200mm c/c",
        "axial_force_label": "Nu",
        "N_ult_total_kN": 1200.0,
        "N_rd_kN": 1800.0,
        "axial_resistance_status": "PASS",
        "is_short": True,
        "moment_status": "PASS",
    }
    data = generate_column_dxf(fake, b=400, h=400, cover=25, code="BS8110")
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    circles = [e for e in doc.modelspace() if e.dxftype() == "CIRCLE"]
    assert len(circles) == 12
