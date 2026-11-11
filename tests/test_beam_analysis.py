"""Validates the general slope-deflection continuous-beam solver against
known, independently-verifiable results — not just internal consistency.
These are the same class of check used throughout this project (compare
against a trusted external reference before trusting new engineering code).
"""
from core.beam_analysis import analyze_continuous_beam, SpanInput


def test_single_span_matches_simple_beam_theory():
    # Trivial case: a single simply-supported span must reduce to the
    # textbook wL^2/8 midspan moment with zero support moments.
    w, L = 10.0, 6.0
    r = analyze_continuous_beam([SpanInput(length_m=L, I_relative=1.0, w_ult_kn_m=w)])
    assert abs(r[0].M_left_support_kNm) < 1e-6
    assert abs(r[0].M_right_support_kNm) < 1e-6
    assert abs(r[0].M_span_max_kNm - (w * L ** 2 / 8)) < 1e-6


def test_two_equal_spans_matches_classic_result():
    # Classic exact elastic result for two equal spans, full UDL, both ends
    # simply supported: middle support moment = wL^2/8; max span moment =
    # 9wL^2/128. These are well-known, independently checkable values.
    w, L = 10.0, 6.0
    r = analyze_continuous_beam([
        SpanInput(length_m=L, I_relative=1.0, w_ult_kn_m=w),
        SpanInput(length_m=L, I_relative=1.0, w_ult_kn_m=w),
    ])
    assert abs(r[0].M_right_support_kNm - (w * L ** 2 / 8)) < 1e-3
    assert abs(r[1].M_left_support_kNm - (w * L ** 2 / 8)) < 1e-3
    assert abs(r[0].M_span_max_kNm - (9 * w * L ** 2 / 128)) < 1e-3
    assert abs(r[1].M_span_max_kNm - (9 * w * L ** 2 / 128)) < 1e-3


def test_three_equal_spans_matches_classic_exact_elastic_result():
    # Classic exact elastic result for three equal spans, full UDL on all
    # spans, both ends simply supported: both interior support moments =
    # wL^2/10 exactly (a standard, independently-verifiable textbook value).
    w, L = 10.0, 6.0
    r = analyze_continuous_beam([SpanInput(length_m=L, I_relative=1.0, w_ult_kn_m=w) for _ in range(3)])
    expected = w * L ** 2 / 10
    assert abs(r[0].M_right_support_kNm - expected) < 1e-3
    assert abs(r[1].M_left_support_kNm - expected) < 1e-3
    assert abs(r[1].M_right_support_kNm - expected) < 1e-3
    assert abs(r[2].M_left_support_kNm - expected) < 1e-3


def test_unequal_spans_satisfy_moment_equilibrium_at_shared_supports():
    # For genuinely unequal spans and unequal stiffness (no known textbook
    # closed-form to compare against), the strongest available correctness
    # check is that adjacent spans agree exactly on the moment at the
    # support they share — anything else would violate basic equilibrium.
    r = analyze_continuous_beam([
        SpanInput(length_m=4.0, I_relative=1.5, w_ult_kn_m=15.0),
        SpanInput(length_m=7.0, I_relative=1.0, w_ult_kn_m=15.0),
        SpanInput(length_m=5.0, I_relative=1.5, w_ult_kn_m=15.0),
    ])
    assert abs(r[0].M_right_support_kNm - r[1].M_left_support_kNm) < 1e-6
    assert abs(r[1].M_right_support_kNm - r[2].M_left_support_kNm) < 1e-6
    # End supports (simply supported, no cantilever) must have zero moment.
    assert abs(r[0].M_left_support_kNm) < 1e-6
    assert abs(r[2].M_right_support_kNm) < 1e-6
    # All span moments must be physically positive (sagging) for a
    # downward-UDL-only case with no cantilevers.
    for span in r:
        assert span.M_span_max_kNm > 0


def test_arbitrary_span_count_is_not_capped():
    # The whole point of replacing the coefficient-table method: this must
    # work for any number of spans, not just up to 3.
    spans = [SpanInput(length_m=5.0, I_relative=1.0, w_ult_kn_m=12.0) for _ in range(7)]
    r = analyze_continuous_beam(spans)
    assert len(r) == 7
    for span in r:
        assert span.M_span_max_kNm > 0


def test_envelope_matches_all_loaded_case_when_there_is_no_live_load():
    # With qk=0, pattern loading has nothing to alternate — the envelope
    # must reduce exactly to the plain all-spans-loaded classic result.
    from core.beam_analysis import envelope_analysis, SpanLoadInput
    w, L = 10.0, 6.0
    r = envelope_analysis([
        SpanLoadInput(length_m=L, I_relative=1.0, gk_kn_m=w, qk_kn_m=0.0, gamma_g=1.0, gamma_q=1.6)
        for _ in range(3)
    ])
    expected = w * L ** 2 / 10
    assert abs(r[0].M_right_support_kNm - expected) < 1e-3


def test_pattern_loading_governs_over_all_spans_loaded_when_live_load_present():
    # SAFETY-CRITICAL regression test: for a continuous beam with real live
    # load, the governing (envelope) span moment MUST be higher than the
    # naive "load every span at once" result — alternate-span loading is
    # what actually governs. If a future change silently drops pattern
    # loading, this test must fail, because that would be an unconservative
    # (unsafe) design change, not just a precision regression.
    from core.beam_analysis import envelope_analysis, SpanLoadInput
    L, gk, qk = 6.0, 6.0, 8.0
    envelope = envelope_analysis([
        SpanLoadInput(length_m=L, I_relative=1.0, gk_kn_m=gk, qk_kn_m=qk, gamma_g=1.4, gamma_q=1.6)
        for _ in range(3)
    ])
    all_loaded = analyze_continuous_beam([
        SpanInput(length_m=L, I_relative=1.0, w_ult_kn_m=1.4 * gk + 1.6 * qk) for _ in range(3)
    ])
    assert envelope[0].M_span_max_kNm > all_loaded[0].M_span_max_kNm
    # Envelope support moments must never be LOWER than the all-loaded case either.
    assert envelope[0].M_right_support_kNm >= all_loaded[0].M_right_support_kNm - 1e-6
