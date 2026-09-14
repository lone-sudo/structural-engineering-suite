"""General continuous-beam analysis via the slope-deflection method.

Replaces the equal-span coefficient-table approach with a real structural
analysis: solves for joint rotations at every support, then derives support
and span moments directly. This correctly handles ANY number of spans,
each with its own length and its own stiffness (independent width/depth per
span) — unequal spans redistribute moment according to their actual
relative stiffness, not a table lookup that assumes they're all the same.

Scope: simply-supported end conditions only (no fixed/built-in ends), no
support settlement, uniformly distributed load only per span (no point
loads yet), all supports assumed rigid (no column/frame flexibility — this
is a continuous-beam-on-supports analysis, not a full frame analysis).
Cantilever overhangs are a separate, not-yet-implemented boundary
condition — see core/standards.py-adjacent modules for that when added.

Sign convention: clockwise-positive end moments (standard slope-deflection
convention). Reported results are converted to the usual "sagging positive"
beam design convention (positive = tension on the bottom face).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List
import numpy as np


@dataclass
class SpanInput:
    length_m: float
    I_relative: float  # any consistent relative stiffness measure (e.g. b*h^3/12); E cancels
    w_ult_kn_m: float  # ultimate factored UDL for this span


@dataclass
class SpanResult:
    length_m: float
    M_left_support_kNm: float   # hogging support moment at the left end of this span (magnitude, sagging-negative convention: reported as positive magnitude)
    M_right_support_kNm: float  # hogging support moment at the right end of this span
    M_span_max_kNm: float       # maximum sagging (positive) moment within the span
    x_max_m: float              # location of M_span_max from the left end of this span
    V_left_kN: float
    V_right_kN: float


def analyze_continuous_beam(spans: List[SpanInput]) -> List[SpanResult]:
    """Solves an arbitrary number of unequal, differently-stiff spans, all
    ends simply supported, via the slope-deflection method."""
    n = len(spans)
    if n < 1:
        raise ValueError("At least one span is required.")

    L = [s.length_m for s in spans]
    I = [s.I_relative for s in spans]
    w = [s.w_ult_kn_m for s in spans]
    k = [I[i] / L[i] for i in range(n)]  # relative stiffness EI/L, E=1 (cancels in final moments)

    # Fixed-end moments (clockwise-positive convention): near end negative,
    # far end positive, magnitude wL^2/12.
    FEM_near = [-w[i] * L[i] ** 2 / 12.0 for i in range(n)]
    FEM_far = [w[i] * L[i] ** 2 / 12.0 for i in range(n)]

    n_joints = n + 1
    A = np.zeros((n_joints, n_joints))
    b = np.zeros(n_joints)

    # Joint 0 (left end, simply supported): M_(span0, near) = 0
    #   FEM_near[0] + 2*k0*(2*theta0 + theta1) = 0
    A[0, 0] += 2 * k[0] * 2
    A[0, 1] += 2 * k[0] * 1
    b[0] = -FEM_near[0]

    # Joint n (right end, simply supported): M_(span n-1, far) = 0
    #   FEM_far[n-1] + 2*k[n-1]*(2*theta_n + theta_(n-1)) = 0
    A[n, n] += 2 * k[n - 1] * 2
    A[n, n - 1] += 2 * k[n - 1] * 1
    b[n] = -FEM_far[n - 1]

    # Interior joints j = 1..n-1: M_(span j-1, far at j) + M_(span j, near at j) = 0
    for j in range(1, n):
        # far end of span (j-1), evaluated at joint j: FEM_far[j-1] + 2*k[j-1]*(2*theta_j + theta_(j-1))
        A[j, j] += 2 * k[j - 1] * 2
        A[j, j - 1] += 2 * k[j - 1] * 1
        rhs = -FEM_far[j - 1]
        # near end of span j, evaluated at joint j: FEM_near[j] + 2*k[j]*(2*theta_j + theta_(j+1))
        A[j, j] += 2 * k[j] * 2
        A[j, j + 1] += 2 * k[j] * 1
        rhs += -FEM_near[j]
        b[j] = rhs

    theta = np.linalg.solve(A, b)

    def M_near(i):
        return FEM_near[i] + 2 * k[i] * (2 * theta[i] + theta[i + 1])

    def M_far(i):
        return FEM_far[i] + 2 * k[i] * (2 * theta[i + 1] + theta[i])

    results = []
    for i in range(n):
        # Convert clockwise-positive end moments to physical hogging support
        # moment magnitudes (support moments are always hogging under
        # downward UDL on a continuous beam with no applied end moments).
        M_left_support = -M_near(i)
        M_right_support = M_far(i)

        # Span bending moment (sagging-positive) = simple-span moment minus
        # the linear moment contributed by the end (hogging) moments.
        Li, wi = L[i], w[i]

        def M_span(x):
            m_simple = wi * x * (Li - x) / 2.0
            m_ends = M_left_support * (1 - x / Li) + M_right_support * (x / Li)
            return m_simple - m_ends

        # Max sagging moment: solve dM/dx = 0 for the parabola-minus-linear form.
        # V(x) = wi*(Li/2 - x) - (M_right_support - M_left_support)/Li ... set to zero:
        x_max = Li / 2.0 - (M_right_support - M_left_support) / (wi * Li)
        x_max = min(max(x_max, 0.0), Li)
        M_span_max = M_span(x_max)

        V_left = wi * Li / 2.0 - (M_right_support - M_left_support) / Li
        V_right = wi * Li - V_left

        results.append(SpanResult(
            length_m=Li,
            M_left_support_kNm=round(M_left_support, 4),
            M_right_support_kNm=round(M_right_support, 4),
            M_span_max_kNm=round(M_span_max, 4),
            x_max_m=round(x_max, 4),
            V_left_kN=round(V_left, 4),
            V_right_kN=round(V_right, 4),
        ))
    return results


@dataclass
class SpanLoadInput:
    length_m: float
    I_relative: float
    gk_kn_m: float  # unfactored... actually ultimate-factored dead UDL for this span
    qk_kn_m: float  # ultimate-factored live UDL for this span


def envelope_analysis(spans: List[SpanLoadInput]) -> List[SpanResult]:
    """Runs the standard BS 8110 / EC2 pattern-loading load cases for a
    continuous beam and returns, per span, the ENVELOPE (worst case across
    all load cases) of span moment, each support moment, and each end
    shear. Loading every span simultaneously does NOT give the true
    maximum span moment under live load for a continuous beam — alternating
    load patterns can govern; skipping this would be unconservative.

    gk_kn_m / qk_kn_m here are already ultimate-factored (gamma_g*Gk,
    gamma_q*Qk) so they can be summed/selected directly per load case.

    Load cases run:
    1. All spans loaded (Gk+Qk everywhere) — the base case.
    2. Odd spans at Gk+Qk / even at Gk-only, and the mirror image —
       maximizes span (sagging) moments via alternate-span loading.
    3. Each adjacent pair of spans at Gk+Qk with all others at Gk-only —
       maximizes the hogging moment at the support between that pair.
    """
    n = len(spans)
    if n == 0:
        raise ValueError("At least one span is required.")
    L = [s.length_m for s in spans]
    I = [s.I_relative for s in spans]
    gk = [s.gk_kn_m for s in spans]
    qk = [s.qk_kn_m for s in spans]

    def _run(loads: List[float]) -> List[SpanResult]:
        return analyze_continuous_beam([
            SpanInput(length_m=L[i], I_relative=I[i], w_ult_kn_m=loads[i]) for i in range(n)
        ])

    load_cases: List[List[float]] = []
    load_cases.append([gk[i] + qk[i] for i in range(n)])
    load_cases.append([gk[i] + qk[i] if i % 2 == 0 else gk[i] for i in range(n)])
    load_cases.append([gk[i] + qk[i] if i % 2 == 1 else gk[i] for i in range(n)])
    for i in range(n - 1):
        case = list(gk)
        case[i] = gk[i] + qk[i]
        case[i + 1] = gk[i + 1] + qk[i + 1]
        load_cases.append(case)

    envelope = [
        SpanResult(length_m=L[i], M_left_support_kNm=0.0, M_right_support_kNm=0.0,
                   M_span_max_kNm=0.0, x_max_m=0.0, V_left_kN=0.0, V_right_kN=0.0)
        for i in range(n)
    ]

    for loads in load_cases:
        results = _run(loads)
        for i, r in enumerate(results):
            e = envelope[i]
            e.M_left_support_kNm = max(e.M_left_support_kNm, r.M_left_support_kNm)
            e.M_right_support_kNm = max(e.M_right_support_kNm, r.M_right_support_kNm)
            e.M_span_max_kNm = max(e.M_span_max_kNm, r.M_span_max_kNm)
            e.V_left_kN = max(e.V_left_kN, abs(r.V_left_kN))
            e.V_right_kN = max(e.V_right_kN, abs(r.V_right_kN))
            if r.M_span_max_kNm == e.M_span_max_kNm:
                e.x_max_m = r.x_max_m

    return envelope
