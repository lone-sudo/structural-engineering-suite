"""EC2 anchorage and lap-length helpers.

These compute the *required* bond lengths. Whether enough embedment is
available at a support or a lap location depends on the drawing and the
support width, which this module does not know; callers must check that
separately (the beam module reports the required values and flags them for
detailing review).
"""
from __future__ import annotations

from typing import Dict


def ec2_anchorage(
    bar_dia_mm: float, f_ck: float, f_yk: float,
    eta1: float = 1.0, eta2: float = 1.0, alpha: float = 1.0,
) -> Dict[str, float]:
    """EN 1992-1-1 8.4: basic and design anchorage length in tension.

    Defaults: ribbed bars (eta1 = 1.0), bar diameter <= 32 mm (eta2 = 1.0),
    and all alpha factors = 1.0 (conservative; no cover/confinement benefit).
    """
    if bar_dia_mm <= 0 or f_ck <= 0 or f_yk <= 0:
        raise ValueError("Bar diameter and material strengths must be positive.")
    if f_ck > 50:
        raise ValueError("EC2 anchorage currently supports fck <= 50 MPa only.")

    f_ctm = 0.30 * f_ck ** (2.0 / 3.0)
    f_ctk_005 = 0.7 * f_ctm
    f_ctd = f_ctk_005 / 1.5
    f_bd = 2.25 * eta1 * eta2 * f_ctd
    sigma_sd = f_yk / 1.15
    lb_rqd = (bar_dia_mm / 4.0) * (sigma_sd / f_bd)
    lb_min = max(0.3 * lb_rqd, 10.0 * bar_dia_mm, 100.0)
    lbd = max(alpha * lb_rqd, lb_min)
    return {
        "f_ctm_MPa": f_ctm,
        "f_bd_MPa": f_bd,
        "lb_rqd_mm": lb_rqd,
        "lb_min_mm": lb_min,
        "lbd_mm": lbd,
    }


def ec2_lap(
    bar_dia_mm: float, f_ck: float, f_yk: float,
    alpha6: float = 1.0, eta1: float = 1.0, eta2: float = 1.0,
) -> Dict[str, float]:
    """EN 1992-1-1 8.7.3 lap length l0 (tension, all other alphas = 1.0)."""
    anch = ec2_anchorage(bar_dia_mm, f_ck, f_yk, eta1=eta1, eta2=eta2)
    l0 = max(alpha6 * anch["lb_rqd_mm"], 0.3 * alpha6 * anch["lb_rqd_mm"], 15.0 * bar_dia_mm, 200.0)
    return {**anch, "l0_mm": l0, "alpha6": alpha6}
