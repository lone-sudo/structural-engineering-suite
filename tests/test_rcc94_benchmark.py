"""Benchmark tests against real RCC-series spreadsheet worked examples.

These are not synthetic hand-calculations — the expected values come from
an actual RCC94.xls output (BS 8110 Table 3.14 two-way slab, "Reinforced
Concrete Council" reference spreadsheet), supplied by a user comparing our
engine's output against it directly. Any future change that shifts a
design moment by more than trivial rounding should be caught here.

Panel: 5.80m x 6.50m, h=250mm, fcu=25, fy=500, gk=7.5 (self 6.0 + finishes
1.5), qk=3.0, "Two Adjacent Edges Discontinuous" (edges 1,2 continuous;
edges 3,4 discontinuous).
"""
from elements.slab import TwoWaySlab


def _reference_slab():
    return TwoWaySlab(
        lx=5.80, ly=6.50, h_slab=250, cover=25, gk_finishes=1.5, qk_live=3.0,
        f_cu=25, f_y=500, panel_type="Two Adjacent Edges Discontinuous", code="BS8110"
    )


def test_rcc94_benchmark_design_moments_match_reference_spreadsheet():
    r = _reference_slab().design_panel()

    # RCC94.xls reference values: Short span M=22.1, Long span M=17.5,
    # Edge1 (continuous) M=29.5, Edge2 (continuous) M=23.3 kNm/m.
    assert abs(r["Msx_pos"] - 22.1) < 0.2
    assert abs(r["Msy_pos"] - 17.5) < 0.2
    assert abs(r["Msx_neg"] - 29.5) < 0.2
    assert abs(r["Msy_neg"] - 23.3) < 0.3

    # Loads must match exactly — these are direct inputs, not derived.
    assert r["gk_slab_kpa"] == 7.5
    assert r["gk_self_kpa"] == 6.0
    assert r["gk_finishes_kpa"] == 1.5
    assert r["qk_slab_kpa"] == 3.0
    assert r["n_ult_kpa"] == 15.3


def test_rcc94_benchmark_deflection_screening_uses_continuous_ratio():
    # Regression test for a real bug: this panel type ("Two Adjacent Edges
    # Discontinuous") is continuous on one of its two short-span-direction
    # edges, so BS 8110 Table 3.9's "continuous" basic ratio (26) applies —
    # not "simply supported" (20). The engine previously used 20 for every
    # panel type except the literal string "Interior Panel", which was
    # unnecessarily conservative and disagreed with the RCC94 reference
    # (allowable span/d = 39.21) by about 12%.
    r = _reference_slab().design_panel()
    assert r["actual_span_d"] > 0
    # RCC94 reference: allowable span/d = 39.21. Allow a wider tolerance
    # here since this is explicitly a simplified screening check, not a
    # claim of exact agreement — but it must be in the "continuous" (26)
    # ballpark, not the "simply supported" (20) one.
    assert 37.0 < r["allowable_span_d"] < 43.0
    assert r["deflection_status"] == "PASS"
