"""Strain-compatibility section analysis for reinforced-concrete columns.

The original column module used a straight-line interaction between the
pure-axial capacity and an approximate pure-moment capacity that counted only
the steel couple. That is conservative for many sections but is not a real
N-M interaction diagram and can be wrong near the balance point.

This module builds the uniaxial N-M interaction from first principles:
  * a rectangular concrete stress block (BS 8110: 0.9x at 0.67fcu/1.5;
    EC2: 0.8x at 0.85fck/1.5 for fck <= 50),
  * elastic-perfectly-plastic reinforcement at each bar layer,
  * a plane-strain distribution with the code ultimate concrete strain.

Biaxial bending is then checked using the BS 8110 equivalent-uniaxial method
or the EN 1992-1-1 5.8.9(4) exponent method, but with the *actual* uniaxial
capacities at the applied axial load rather than an approximation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np

from core.standards import BS8110, Eurocode2

ES_MPA = 200_000.0


@dataclass(frozen=True)
class BarLayer:
    """A group of bars at one distance from the compression face."""
    area_mm2: float
    d_mm: float


@dataclass(frozen=True)
class InteractionPoint:
    N_kN: float
    M_kNm: float


def _material(code: str, f_c: float, f_y: float) -> Tuple[float, float, float]:
    """Return (fcd, lambda, fyd) for the selected code."""
    if code == "BS8110":
        # BS 8110 Amendment 6 changed the reinforcement partial factor to
        # 1.05, so the design strength used in the flexure formulae is
        # 0.95fy (the same 0.95fy used in BS8110.design_flexure).
        return 0.67 * f_c / 1.5, 0.9, 0.95 * f_y
    if code == "Eurocode 2":
        if f_c > 50:
            raise ValueError("Section analysis currently supports fck <= 50 MPa only.")
        return 0.85 * f_c / 1.5, 0.8, f_y / 1.15
    raise ValueError(f"Unsupported design code: {code}")


def _response(
    x_mm: float, width_mm: float, depth_mm: float,
    bars: Sequence[BarLayer], fcd: float, lam: float, fyd: float,
) -> Tuple[float, float]:
    """Section response for a neutral-axis depth x from the compression face."""
    x = max(float(x_mm), 1e-6)
    block = min(lam * x, depth_mm)
    Fc = fcd * width_mm * block
    N = Fc
    M = Fc * (depth_mm / 2.0 - block / 2.0)

    for bar in bars:
        eps = 0.0035 * (x - bar.d_mm) / x  # compression positive
        sigma = max(-fyd, min(fyd, ES_MPA * eps))
        Fs = sigma * bar.area_mm2
        N += Fs
        M += Fs * (depth_mm / 2.0 - bar.d_mm)
    return N / 1000.0, abs(M) / 1e6


def interaction_curve(
    width_mm: float, depth_mm: float, bars: Sequence[BarLayer],
    f_c: float, f_y: float, code: str, n_points: int = 180,
) -> List[InteractionPoint]:
    if width_mm <= 0 or depth_mm <= 0:
        raise ValueError("Section dimensions must be positive.")
    if not bars:
        raise ValueError("At least one bar layer is required.")
    fcd, lam, fyd = _material(code, f_c, f_y)

    # Sample the neutral axis from near-zero (pure tension/bending) to well
    # beyond the section (pure compression). The extra high-x points ensure
    # the curve reaches the pure-axial capacity.
    xs = list(np.linspace(0.005 * depth_mm, 1.2 * depth_mm, n_points))
    xs += list(np.linspace(1.2 * depth_mm, 4.0 * depth_mm, max(20, n_points // 4)))
    xs.append(10.0 * depth_mm)
    out = []
    for x in xs:
        N, M = _response(x, width_mm, depth_mm, bars, fcd, lam, fyd)
        out.append(InteractionPoint(N, M))
    return out


def axial_capacity(
    width_mm: float, depth_mm: float, bars: Sequence[BarLayer],
    f_c: float, f_y: float, code: str,
) -> float:
    fcd, _, fyd = _material(code, f_c, f_y)
    return (fcd * width_mm * depth_mm + fyd * sum(b.area_mm2 for b in bars)) / 1000.0


def moment_capacity(
    N_kN: float, width_mm: float, depth_mm: float, bars: Sequence[BarLayer],
    f_c: float, f_y: float, code: str,
) -> float:
    """Maximum uniaxial moment resistance at the applied axial load."""
    curve = interaction_curve(width_mm, depth_mm, bars, f_c, f_y, code)
    N0 = axial_capacity(width_mm, depth_mm, bars, f_c, f_y, code)
    if N_kN > N0 + 1e-6:
        return 0.0

    best = 0.0
    for a, b in zip(curve, curve[1:]):
        if (a.N_kN - N_kN) * (b.N_kN - N_kN) <= 0.0 and abs(b.N_kN - a.N_kN) > 1e-9:
            f = (N_kN - a.N_kN) / (b.N_kN - a.N_kN)
            best = max(best, a.M_kNm + f * (b.M_kNm - a.M_kNm))
    return best


def _axis_layers(
    bars_xy: Iterable[Tuple[float, float, float]],
    axis: str, b_mm: float, h_mm: float,
) -> Tuple[float, float, List[BarLayer]]:
    """Map (x, y, area) bar positions to a uniaxial section.

    For bending about x the compression face is the top (y = h); for bending
    about y it is the right face (x = b). The section is treated as uncracked
    for the interaction diagram, which is the usual column-design assumption.
    """
    layers: Dict[float, float] = {}
    if axis == "x":
        width, depth = b_mm, h_mm
        for _x, y, area in bars_xy:
            d = h_mm - y
            layers[d] = layers.get(d, 0.0) + area
    else:
        width, depth = h_mm, b_mm
        for x, _y, area in bars_xy:
            d = b_mm - x
            layers[d] = layers.get(d, 0.0) + area
    return width, depth, [BarLayer(a, d) for d, a in sorted(layers.items())]


def biaxial_utilization(
    N_kN: float, Mx_kNm: float, My_kNm: float,
    b_mm: float, h_mm: float, bars_xy: Iterable[Tuple[float, float, float]],
    f_c: float, f_y: float, code: str,
    single_axis: bool = False,
) -> Dict[str, float | str]:
    """Check biaxial bending against actual uniaxial capacities at N.

    Returns ``utilization`` (<= 1 passes), ``Mx_Rd``, ``My_Rd`` and the
    method used. ``single_axis`` is used for the code minimum-eccentricity
    case when no applied moments exist; applying e0 about both axes and then
    combining them biaxially double-counts the minimum imperfection.
    """
    bars_xy = list(bars_xy)
    wx, dx, bars_x = _axis_layers(bars_xy, "x", b_mm, h_mm)
    wy, dy, bars_y = _axis_layers(bars_xy, "y", b_mm, h_mm)

    Mx_Rd = moment_capacity(N_kN, wx, dx, bars_x, f_c, f_y, code)
    My_Rd = moment_capacity(N_kN, wy, dy, bars_y, f_c, f_y, code)
    N0 = axial_capacity(wx, dx, bars_x, f_c, f_y, code)

    if N_kN >= N0:
        return {"utilization": float("inf"), "Mx_Rd": Mx_Rd, "My_Rd": My_Rd,
                "method": "axial capacity exceeded"}

    def ratio(M: float, MRd: float) -> float:
        if MRd <= 0:
            return 0.0 if M == 0 else float("inf")
        return M / MRd

    ux, uy = ratio(Mx_kNm, Mx_Rd), ratio(My_kNm, My_Rd)
    if single_axis:
        return {"utilization": max(ux, uy), "Mx_Rd": Mx_Rd, "My_Rd": My_Rd,
                "method": "governing uniaxial capacity"}

    if code == "BS8110":
        n_ratio = min(0.6, max(0.0, N_kN * 1000.0 / (b_mm * h_mm * f_c)))
        beta = BS8110.biaxial_beta(n_ratio)
        Mx_eff = Mx_kNm + beta * (h_mm / b_mm) * My_kNm
        My_eff = My_kNm + beta * (b_mm / h_mm) * Mx_kNm
        ux_eff = ratio(Mx_eff, Mx_Rd)
        uy_eff = ratio(My_eff, My_Rd)
        return {"utilization": max(ux_eff, uy_eff), "Mx_Rd": Mx_Rd, "My_Rd": My_Rd,
                "beta": beta, "method": "BS 8110 Cl. 3.8.4.5 equivalent uniaxial"}

    a = Eurocode2.biaxial_exponent(N_kN / N0 if N0 > 0 else 1.0)
    return {"utilization": ux ** a + uy ** a, "Mx_Rd": Mx_Rd, "My_Rd": My_Rd,
            "a": a, "method": "EN 1992-1-1 Cl. 5.8.9(4) exponent"}
