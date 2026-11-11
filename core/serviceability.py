"""Serviceability helpers: cracked-section stress and EC2 crack width.

EN 1992-1-1 Cl. 7.3.4 is implemented for the quasi-permanent combination.
BS 8110 crack-width control is *not* implemented; callers must report that
check as NOT CHECKED rather than pretending the EC2 result covers it.
"""
from __future__ import annotations

import math
from typing import Dict

ES_MPA = 200_000.0


def _e_cm(code: str, f_c: float) -> float:
    if code == "Eurocode 2":
        f_cm = f_c + 8.0
        return 22.0 * (f_cm / 10.0) ** 0.3 * 1000.0  # MPa
    # BS 8110-2 short-term modulus for normal-weight concrete (GPa).
    return (20.0 + 0.2 * f_c) * 1000.0


def cracked_section_stress(
    M_kNm: float, b_mm: float, d_mm: float, As_mm2: float,
    f_c: float, code: str,
) -> Dict[str, float]:
    """Elastic cracked-section steel/concrete stress for a singly reinforced section."""
    if M_kNm <= 0 or As_mm2 <= 0 or b_mm <= 0 or d_mm <= 0:
        return {"sigma_s": 0.0, "sigma_c": 0.0, "x_mm": 0.0, "Icr_mm4": 0.0,
                "Ecm_MPa": _e_cm(code, f_c), "alpha_e": 0.0}

    Ecm = _e_cm(code, f_c)
    alpha_e = ES_MPA / Ecm
    # b x^2 / 2 = alpha_e As (d - x)
    a = 0.5 * b_mm
    bq = alpha_e * As_mm2
    c = -alpha_e * As_mm2 * d_mm
    x = (-bq + math.sqrt(bq * bq - 4.0 * a * c)) / (2.0 * a)
    Icr = b_mm * x ** 3 / 3.0 + alpha_e * As_mm2 * (d_mm - x) ** 2

    M_Nmm = M_kNm * 1e6
    sigma_s = alpha_e * M_Nmm * (d_mm - x) / Icr
    sigma_c = M_Nmm * x / Icr
    return {
        "sigma_s": sigma_s,
        "sigma_c": sigma_c,
        "x_mm": x,
        "Icr_mm4": Icr,
        "Ecm_MPa": Ecm,
        "alpha_e": alpha_e,
    }


def ec2_crack_width(
    M_qp_kNm: float, b_mm: float, h_mm: float, d_mm: float, As_mm2: float,
    bar_dia_mm: float, cover_mm: float, f_ck: float, f_yk: float,
    w_limit_mm: float = 0.3,
) -> Dict[str, float | str]:
    """EN 1992-1-1 Cl. 7.3.4 crack width under the quasi-permanent moment.

    ``cover_mm`` is the concrete cover to the longitudinal bar (for a beam,
    nominal cover plus link diameter). The result is a screening value, not a
    substitute for a project-specific crack-width calculation with the actual
    bond and restraint conditions.
    """
    if M_qp_kNm <= 0 or As_mm2 <= 0:
        return {"wk_mm": 0.0, "status": "N/A", "sigma_s": 0.0,
                "message": "No positive quasi-permanent moment — crack width not applicable."}

    stress = cracked_section_stress(M_qp_kNm, b_mm, d_mm, As_mm2, f_ck, "Eurocode 2")
    sigma_s = stress["sigma_s"]
    x = stress["x_mm"]
    if sigma_s <= 0:
        return {"wk_mm": 0.0, "status": "PASS", "sigma_s": 0.0,
                "message": "Section uncracked under the quasi-permanent moment."}

    f_ctm = 0.30 * f_ck ** (2.0 / 3.0)
    h_eff = min(2.5 * (h_mm - d_mm), (h_mm - x) / 3.0, h_mm / 2.0)
    h_eff = max(h_eff, 1.0)
    rho_p_eff = As_mm2 / (b_mm * h_eff)

    k1, k2, k3, k4 = 0.8, 0.5, 3.4, 0.425
    sr_max = k3 * cover_mm + k1 * k2 * k4 * bar_dia_mm / max(rho_p_eff, 1e-9)
    eps_diff = (
        sigma_s - 0.4 * f_ctm / max(rho_p_eff, 1e-9) * (1.0 + stress["alpha_e"] * rho_p_eff)
    ) / ES_MPA
    eps_diff = max(eps_diff, 0.6 * sigma_s / ES_MPA)
    wk = sr_max * eps_diff
    status = "PASS" if wk <= w_limit_mm else "FAIL"

    return {
        "wk_mm": wk,
        "status": status,
        "sigma_s": sigma_s,
        "sr_max_mm": sr_max,
        "rho_p_eff": rho_p_eff,
        "h_eff_mm": h_eff,
        "eps_diff": eps_diff,
        "w_limit_mm": w_limit_mm,
        "x_mm": x,
        "message": (
            f"EN 1992-1-1 7.3.4: wk = {wk:.3f} mm vs limit {w_limit_mm:.2f} mm "
            f"(sigma_s = {sigma_s:.1f} MPa)."
        ),
    }
