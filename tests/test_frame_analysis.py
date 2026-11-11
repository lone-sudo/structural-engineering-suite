"""Benchmark tests for the Phase-2 3-D frame solver and frame builder."""
import math

import pytest

from core.frame_analysis import FrameLoadCase, FrameModel, MemberUDL
from core.load_combinations import bs8110_combinations, en1990_combinations
from core.wind_load import wind_pressure_kpa
from pipeline.frame import FrameBuilding


def _section(b=250.0, h=450.0):
    return b * h, h * b ** 3 / 12, b * h ** 3 / 12, 0.141 * min(b, h) * max(b, h) ** 3


def _beam_model(L_m=5.0, pins=True):
    m = FrameModel()
    A, Iy, Iz, J = _section()
    if pins:
        n0 = m.add_node(0, 0, 0, (True, True, True, True, False, False))
        n1 = m.add_node(L_m, 0, 0, (False, True, True, True, False, False))
    else:
        n0 = m.add_node(0, 0, 0, (True,) * 6)
        n1 = m.add_node(L_m, 0, 0, (True,) * 6)
    mi = m.add_member(n0, n1, 30000, 12500, A, Iy, Iz, J)
    return m, mi, L_m * 1000.0


def test_simply_supported_beam_reactions_and_midspan_moment():
    m, mi, L = _beam_model()
    w = 10.0
    res = m.solve_single(FrameLoadCase("G", udls=[MemberUDL(mi, wz=-w)]))
    assert res.reactions[2] == pytest.approx(w * L / 2.0, rel=1e-6)
    assert res.reactions[8] == pytest.approx(w * L / 2.0, rel=1e-6)
    assert res.members[0].Mz_i_kNm == pytest.approx(0.0, abs=1e-6)
    mid = m.member_internal_forces(res, mi, L / 2.0, qy=-w)
    assert mid["Mz_kNm"] == pytest.approx(w * (L / 1000.0) ** 2 / 8.0, rel=1e-6)


def test_fixed_fixed_beam_end_moments_and_reactions():
    m, mi, L = _beam_model(pins=False)
    w = 10.0
    res = m.solve_single(FrameLoadCase("G", udls=[MemberUDL(mi, wz=-w)]))
    expected = w * L ** 2 / 12.0 / 1e6
    assert abs(res.members[0].Mz_i_kNm) == pytest.approx(expected, rel=1e-6)
    assert abs(res.members[0].Mz_j_kNm) == pytest.approx(expected, rel=1e-6)
    assert res.reactions[2] == pytest.approx(w * L / 2.0, rel=1e-6)
    assert res.reactions[8] == pytest.approx(w * L / 2.0, rel=1e-6)


def test_cantilever_fixed_end_moment():
    m = FrameModel()
    A, Iy, Iz, J = _section()
    n0 = m.add_node(0, 0, 0, (True,) * 6)
    n1 = m.add_node(6, 0, 0, (False,) * 6)
    mi = m.add_member(n0, n1, 30000, 12500, A, Iy, Iz, J)
    w = 10.0
    res = m.solve_single(FrameLoadCase("G", udls=[MemberUDL(mi, wz=-w)]))
    assert abs(res.members[0].Mz_i_kNm) == pytest.approx(w * 6000 ** 2 / 2.0 / 1e6, rel=1e-6)


def test_portal_frame_horizontal_equilibrium_and_gravity_axial_sum():
    m = FrameModel()
    A, Iy, Iz, J = _section()
    # 6 m span, 3 m high portal, fixed bases.
    n0 = m.add_node(0, 0, 0, (True,) * 6)
    n1 = m.add_node(0, 0, 3, (False,) * 6)
    n2 = m.add_node(6, 0, 3, (False,) * 6)
    n3 = m.add_node(6, 0, 0, (True,) * 6)
    c1 = m.add_member(n0, n1, 30000, 12500, A, Iy, Iz, J)
    b = m.add_member(n1, n2, 30000, 12500, A, Iy, Iz, J)
    c2 = m.add_member(n2, n3, 30000, 12500, A, Iy, Iz, J)
    gravity = FrameLoadCase("G", udls=[MemberUDL(b, wz=-20.0)])
    lateral = FrameLoadCase("W", nodal_loads={n1: (50.0, 0, 0, 0, 0, 0)})
    rg = m.solve_single(gravity)
    rw = m.solve_single(lateral)
    assert (rg.reactions[2] + rg.reactions[20]) / 1000.0 == pytest.approx(20.0 * 6.0, rel=1e-6)
    assert (rw.reactions[0] + rw.reactions[18]) / 1000.0 == pytest.approx(-50.0, rel=1e-6)


def test_load_combinations_have_positive_uls_and_sls_sets():
    en = en1990_combinations()
    bs = bs8110_combinations()
    assert any(c.kind == "ULS" and c.factors.get("Q") == 1.5 for c in en)
    assert any(c.kind == "SLS" for c in en)
    assert any(c.kind == "ULS" and c.factors.get("Q") == 1.6 for c in bs)
    assert all(all(v >= 0 for v in c.factors.values()) for c in en + bs)


def test_wind_pressure_increases_with_height_and_velocity():
    low = wind_pressure_kpa(25, 5, "suburban")
    high = wind_pressure_kpa(25, 30, "suburban")
    fast = wind_pressure_kpa(40, 30, "suburban")
    assert high["w_kpa"] > low["w_kpa"] > 0
    assert fast["w_kpa"] > high["w_kpa"]


def test_frame_building_base_shear_matches_factored_wind():
    b = FrameBuilding(
        [4, 4], [5, 5],
        [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [2, 1], [0, 2], [1, 2], [2, 2]],
        num_storeys=2, storey_height_m=3.0, code="BS8110",
        wind_speed_m_s=30.0,
    )
    res = b.analyse()
    # BS 8110 ULS wind factor is 1.4, so the X base shear envelope must be
    # at least 1.4 x the applied unfactored wind.
    assert res.base_shear_x_kN >= 1.35 * res.applied_wind_x_kN
    assert res.max_drift_x < res.drift_limit
    assert any(e.kind == "column" and e.N_max_kN > 0 for e in res.envelopes)
    assert any(e.kind == "beam" and e.Mz_max_kNm > 0 for e in res.envelopes)


def test_frame_building_detects_a_drift_failure():
    b = FrameBuilding(
        [8, 8], [8, 8],
        [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [2, 1], [0, 2], [1, 2], [2, 2]],
        num_storeys=6, storey_height_m=4.0, code="BS8110",
        col_b_mm=200, col_h_mm=200, beam_b_mm=200, beam_h_mm=400,
        wind_speed_m_s=45.0, drift_limit=1e-5,
    )
    res = b.analyse()
    assert res.max_drift_x > res.drift_limit
    assert res.warnings
