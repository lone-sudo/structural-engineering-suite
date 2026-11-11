from __future__ import annotations

import math
from typing import Dict


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be > 0; got {value}")


class BS8110:
    """BS 8110-1:1997 calculation helpers.

    Important: BS 8110 is withdrawn in the UK. These routines are retained for
    projects that explicitly specify BS 8110 and must be independently checked.
    They do not claim compliance with a current national building regulation.
    """

    @staticmethod
    def load_factors() -> tuple[float, float]:
        return 1.4, 1.6

    @staticmethod
    def design_flexure(
        M_u: float, b: float, d: float, f_cu: float, f_y: float,
        d_prime: float = 0.0, min_steel_h: float | None = None
    ) -> Dict[str, float | str]:
        for n, v in (("b", b), ("d", d), ("fcu", f_cu), ("fy", f_y)):
            _require_positive(n, v)
        if d <= d_prime:
            raise ValueError("Effective depth d must exceed d_prime.")

        M = abs(M_u) * 1e6
        K = M / (b * d**2 * f_cu)
        K_prime = 0.156

        if K <= K_prime:
            z_factor = 0.5 + math.sqrt(max(0.0, 0.25 - K / 0.9))
            z = min(0.95 * d, z_factor * d)
            As_req = M / (0.95 * f_y * z) if M else 0.0
            As_comp = 0.0
            section_type = "Singly Reinforced"
        else:
            z = 0.775 * d
            M_prime = K_prime * f_cu * b * d**2
            As_comp = max(
                0.0, (M - M_prime) / (0.95 * f_y * (d - d_prime))
            )
            As_req = M_prime / (0.95 * f_y * z) + As_comp
            section_type = "Doubly Reinforced"

        # BS 8110 Table 3.25: for a rectangular section the minimum tension
        # steel is 0.13% of the gross concrete area (b*h) for fy = 460 MPa,
        # but 0.24% for fy = 250 MPa. The previous implementation always used
        # 0.13%, which under-provides by ~46% when the engineer selects
        # mild steel. Callers that know the overall depth pass min_steel_h;
        # otherwise retain the historical d-based fallback for compatibility.
        gross_depth = min_steel_h if min_steel_h is not None else d
        _require_positive("min_steel_h", gross_depth)
        min_pct = 0.0024 if f_y <= 250.0 else 0.0013
        As_min = min_pct * b * gross_depth
        As_req = max(As_req, As_min)

        return {
            "K": K,
            "z": z,
            "As_req": As_req,
            "As_comp": As_comp,
            "As_min": As_min,
            "section_type": section_type,
            "fcd_used": 0.0,
        }

    @staticmethod
    def design_shear(
        V_u: float, b_v: float, d: float, f_cu: float, f_yv: float,
        As_prov: float
    ) -> Dict[str, float | str]:
        for n, v in (("bv", b_v), ("d", d), ("fcu", f_cu), ("fyv", f_yv)):
            _require_positive(n, v)
        if As_prov <= 0:
            raise ValueError("As_prov must be > 0 for shear design.")

        v = abs(V_u) * 1e3 / (b_v * d)
        v_max = min(0.8 * math.sqrt(f_cu), 5.0)
        if v > v_max:
            return {
                "status": "FAIL", "v": v, "vc": 0.0,
                "asv_sv_req": 0.0, "v_max": v_max,
                "message": "Concrete shear stress exceeds the adopted BS 8110 maximum."
            }

        p = min(3.0, 100.0 * As_prov / (b_v * d))
        d_factor = (400.0 / d) ** 0.25 if d < 400 else 1.0
        fcu_factor = (min(f_cu, 40.0) / 25.0) ** (1 / 3)
        vc = (0.79 * p ** (1 / 3) * d_factor * fcu_factor) / 1.25

        if v < 0.5 * vc:
            asv_sv = 0.0
            message = "Nominal shear links govern; minimum links and spacing rules still apply."
        elif v <= vc + 0.4:
            asv_sv = (0.4 * b_v) / (0.95 * f_yv)
            message = "Minimum shear reinforcement governs."
        else:
            asv_sv = b_v * (v - vc) / (0.95 * f_yv)
            message = "Designed shear reinforcement required."

        return {
            "status": "PASS", "v": v, "vc": vc,
            "asv_sv_req": asv_sv, "v_max": v_max, "message": message
        }

    @staticmethod
    def concrete_shear_stress(b_v: float, d: float, f_cu: float, As_prov: float) -> float:
        """vc per BS 8110 Table 3.8, reusable for both beam and punching screening."""
        for n, v in (("bv", b_v), ("d", d), ("fcu", f_cu)):
            _require_positive(n, v)
        if As_prov <= 0:
            raise ValueError("As_prov must be > 0.")
        p = min(3.0, 100.0 * As_prov / (b_v * d))
        d_factor = (400.0 / d) ** 0.25 if d < 400 else 1.0
        fcu_factor = (min(f_cu, 40.0) / 25.0) ** (1 / 3)
        return (0.79 * p ** (1 / 3) * d_factor * fcu_factor) / 1.25

    @staticmethod
    def deflection_check(
        b: float, d: float, M_u: float, As_req: float, As_prov: float,
        f_y: float, basic_ratio: float = 20.0
    ) -> Dict[str, float | str]:
        """Simplified BS 8110 Part 1 3.4.6 span/effective-depth screening check.

        basic_ratio: 20.0 simply supported, 26.0 continuous, 7.0 cantilever
        (rectangular sections, Table 3.9). Returns an allowable span/d ratio;
        callers compare it against the member's actual span/d. This is a
        screening check only, not a full deflection calculation.
        """
        for n, v in (("b", b), ("d", d), ("As_prov", As_prov), ("fy", f_y)):
            _require_positive(n, v)
        M_bd2 = (abs(M_u) * 1e6) / (b * d**2) if M_u else 0.0
        As_req_eff = max(As_req, 1e-9)
        fs = (2.0 / 3.0) * f_y * (As_req_eff / As_prov)
        mf = min(2.0, 0.55 + (477.0 - fs) / (120.0 * (0.9 + M_bd2)))
        mf = max(mf, 0.0)
        allowable_span_d = basic_ratio * mf
        return {"allowable_span_d": allowable_span_d, "modification_factor": mf}


    @staticmethod
    def min_eccentricity_mm(h: float) -> float:
        """BS 8110-1:1997 Cl. 3.8.2.4: emin = 0.05h, not more than 20mm."""
        _require_positive("h", h)
        return min(0.05 * h, 20.0)

    @staticmethod
    def additional_moment_kNm(N_ult_kN: float, le_mm: float, dim_mm: float) -> float:
        """BS 8110-1:1997 Cl. 3.8.3.1 simplified additional moment for a slender
        braced column (K=1.0 taken conservatively, i.e. no reduction for low
        axial load): au = (1/2000)(le/dim)^2 * dim, Madd = N * au."""
        for n, v in (("le", le_mm), ("dim", dim_mm)):
            _require_positive(n, v)
        au_mm = (1.0 / 2000.0) * (le_mm / dim_mm) ** 2 * dim_mm
        return N_ult_kN * (au_mm / 1000.0)

    @staticmethod
    def biaxial_beta(n_ratio: float) -> float:
        """BS 8110-1:1997 Table 3.24 beta factor for the biaxial-to-uniaxial
        equivalent moment method (Cl. 3.8.4.5), linearly interpolated."""
        table = [(0.0, 1.00), (0.1, 0.88), (0.2, 0.77), (0.3, 0.65),
                 (0.4, 0.53), (0.5, 0.42), (0.6, 0.30)]
        n_ratio = max(0.0, min(n_ratio, 0.6))
        for (n0, b0), (n1, b1) in zip(table, table[1:]):
            if n0 <= n_ratio <= n1:
                return b0 + (b1 - b0) * (n_ratio - n0) / (n1 - n0)
        return 0.30


class Eurocode2:
    """EN 1992-1-1 flexural helpers.

    The implementation uses the rectangular stress-block approach for
    fck <= 50 MPa and explicit alpha_cc / gamma factors. National Annex
    choices should be supplied by the project rather than hidden in code.
    """

    @staticmethod
    def load_factors() -> tuple[float, float]:
        return 1.35, 1.50

    @staticmethod
    def design_flexure(
        M_Ed: float, b: float, d: float, f_ck: float, f_yk: float,
        d_prime: float = 0.0, alpha_cc: float = 0.85,
        gamma_c: float = 1.5, gamma_s: float = 1.15
    ) -> Dict[str, float | str]:
        for n, v in (("b", b), ("d", d), ("fck", f_ck), ("fyk", f_yk)):
            _require_positive(n, v)
        if d <= d_prime:
            raise ValueError("Effective depth d must exceed d_prime.")
        if f_ck > 50:
            raise ValueError(
                "This simplified rectangular-block routine currently supports fck <= 50 MPa."
            )

        eta = 1.0
        lam = 0.8
        f_cd = alpha_cc * f_ck / gamma_c
        f_yd = f_yk / gamma_s
        M = abs(M_Ed) * 1e6

        # K = eta*fcd*lambda*xi*(1-0.4*xi)
        K = M / (b * d**2 * f_cd) if M else 0.0
        xi_bal = 0.45
        K_bal = eta * lam * xi_bal * (1 - 0.4 * xi_bal)

        if K <= K_bal:
            a = 0.4
            # Solve 0.8*xi*(1-0.4xi)=K.
            A = eta * lam * a
            B = -eta * lam
            C = K
            disc = max(0.0, B * B - 4 * A * C)
            xi = (-B - math.sqrt(disc)) / (2 * A)
            z = d * (1 - 0.4 * xi)
            As_req = M / (f_yd * z) if M else 0.0
            As_comp = 0.0
            section_type = "Singly Reinforced"
        else:
            z = d * (1 - 0.4 * xi_bal)
            M_bal = K_bal * f_cd * b * d**2
            As_t_bal = M_bal / (f_yd * z)
            As_comp = (M - M_bal) / (f_yd * max(d - d_prime, 1e-9))
            As_req = As_t_bal + As_comp
            section_type = "Doubly Reinforced"

        # EC2 9.2.1.1 minimum tension reinforcement.
        f_ctm = 0.30 * f_ck ** (2 / 3)
        As_min = max(0.26 * f_ctm / f_yk * b * d, 0.0013 * b * d)
        As_req = max(As_req, As_min)

        return {
            "K": K,
            "K_bal": K_bal,
            "z": z,
            "As_req": As_req,
            "As_comp": max(0.0, As_comp),
            "As_min": As_min,
            "f_cd": f_cd,
            "f_yd": f_yd,
            "section_type": section_type,
        }

    @staticmethod
    def concrete_shear_capacity(
        b_w: float, d: float, f_ck: float, As_prov: float, gamma_c: float = 1.5
    ) -> float:
        """v_Rd,c per EN 1992-1-1 6.2.2, without axial load (N_Ed = 0)."""
        for n, v in (("bw", b_w), ("d", d), ("fck", f_ck)):
            _require_positive(n, v)
        if As_prov <= 0:
            raise ValueError("As_prov must be > 0.")
        k = min(2.0, 1 + math.sqrt(200.0 / d))
        rho_l = min(0.02, As_prov / (b_w * d))
        C_rdc = 0.18 / gamma_c
        v_min = 0.035 * k ** 1.5 * math.sqrt(f_ck)
        v_rdc = C_rdc * k * (100 * rho_l * f_ck) ** (1 / 3)
        return max(v_rdc, v_min)

    @staticmethod
    def design_shear(
        V_Ed: float, b_w: float, d: float, f_ck: float, f_ywk: float,
        As_prov: float, gamma_c: float = 1.5, gamma_s: float = 1.15,
        theta_deg: float = 21.8
    ) -> Dict[str, float | str]:
        """EN 1992-1-1 6.2 shear design (variable strut inclination method).

        theta_deg defaults to the common minimum strut angle (cot(theta)=2.5).
        Members without calculated shear reinforcement still require the
        code's minimum shear reinforcement ratio and spacing rules.
        """
        for n, v in (("bw", b_w), ("d", d), ("fck", f_ck), ("fywk", f_ywk)):
            _require_positive(n, v)
        if As_prov <= 0:
            raise ValueError("As_prov must be > 0 for shear design.")

        v_ed_stress = abs(V_Ed) * 1e3 / (b_w * d)
        v_rdc = Eurocode2.concrete_shear_capacity(b_w, d, f_ck, As_prov, gamma_c)

        f_cd = 0.85 * f_ck / gamma_c  # alpha_cc default
        nu1 = 0.6 * (1 - f_ck / 250.0)
        theta = math.radians(theta_deg)
        v_rd_max = (0.9 * d) * b_w * nu1 * f_cd * (1 / (1 / math.tan(theta) + math.tan(theta))) / 1e3
        v_rd_max_stress = v_rd_max * 1e3 / (b_w * d)

        if v_ed_stress > v_rd_max_stress:
            return {
                "status": "FAIL", "v": v_ed_stress, "vrdc": v_rdc,
                "asw_sv_req": 0.0, "v_rd_max": v_rd_max_stress,
                "message": "Applied shear exceeds the concrete strut crushing capacity (V_Rd,max)."
            }

        if v_ed_stress <= v_rdc:
            return {
                "status": "PASS", "v": v_ed_stress, "vrdc": v_rdc,
                "asw_sv_req": 0.0, "v_rd_max": v_rd_max_stress,
                "message": "No calculated shear reinforcement required; minimum links and spacing rules still apply."
            }

        f_ywd = f_ywk / gamma_s
        V_ed_n = abs(V_Ed) * 1e3
        asw_sv = V_ed_n / (0.9 * d * f_ywd * (1 / math.tan(theta)))
        return {
            "status": "PASS", "v": v_ed_stress, "vrdc": v_rdc,
            "asw_sv_req": asw_sv, "v_rd_max": v_rd_max_stress,
            "message": "Designed shear reinforcement required (variable strut inclination method, cot(theta)=2.5)."
        }

    @staticmethod
    def min_eccentricity_mm(h: float) -> float:
        """EN 1992-1-1 Cl. 6.1(4): e0 = max(h/30, 20mm)."""
        _require_positive("h", h)
        return max(h / 30.0, 20.0)

    @staticmethod
    def biaxial_exponent(n_ratio: float) -> float:
        """EN 1992-1-1 Cl. 5.8.9(4) exponent 'a' for rectangular sections.

        The code defines three anchor points, not two: a = 1.0 at
        NEd/NRd = 0.1, a = 1.5 at 0.7, and a = 2.0 at 1.0, with linear
        interpolation between them. The previous implementation jumped from
        1.0 to 2.0 over 0.1-0.7, which over-predicted the biaxial resistance
        for moderately loaded columns (a non-conservative error).
        """
        if n_ratio <= 0.1:
            return 1.0
        if n_ratio >= 1.0:
            return 2.0
        if n_ratio <= 0.7:
            return 1.0 + (n_ratio - 0.1) * (1.5 - 1.0) / (0.7 - 0.1)
        return 1.5 + (n_ratio - 0.7) * (2.0 - 1.5) / (1.0 - 0.7)

    @staticmethod
    def span_depth_limit(
        f_ck: float, As_req: float, As_prov: float, b: float, d: float,
        K: float = 1.0, As_comp: float = 0.0, f_yk: float = 500.0,
        F1: float = 1.0, F2: float = 1.0,
    ) -> Dict[str, float]:
        """EN 1992-1-1 Cl. 7.4.2 span/effective-depth deflection screening.

        Expressions (7.16.a)/(7.16.b) give the basic limit N; F1 accounts
        for flanged sections (1.0 for rectangular), F2 for brittle
        partitions and F3 for the actual service steel stress. The UK
        National Annex caps F3 at 1.5 and the final ratio at 40K. This is
        a screening rule, not a calculated deflection.
        """
        for name, value in (("fck", f_ck), ("b", b), ("d", d)):
            _require_positive(name, value)
        if As_req < 0 or As_prov < 0 or As_comp < 0:
            raise ValueError("Reinforcement areas cannot be negative.")
        if As_req == 0:
            As_req = 1e-9

        rho = As_req / (b * d)
        rho_p = As_comp / (b * d)
        rho_0 = math.sqrt(f_ck) / 1000.0

        if rho <= rho_0:
            limit = K * (
                11.0
                + 1.5 * math.sqrt(f_ck) * (rho_0 / rho)
                + 3.2 * math.sqrt(f_ck) * max(0.0, rho_0 / rho - 1.0) ** 1.5
            )
        else:
            denom = max(rho - rho_p, 1e-9)
            limit = K * (
                11.0
                + 1.5 * math.sqrt(f_ck) * rho_0 / denom
                + math.sqrt(f_ck) * math.sqrt(max(rho_p, 0.0) / rho_0) / 12.0
            )

        # EN 1992-1-1 (7.17), with the UK NA cap on F3.
        F3 = min(1.5, 500.0 * As_prov / (f_yk * As_req)) if As_prov > 0 else 1.0
        allowable = min(limit * F1 * F2 * F3, 40.0 * K)
        return {
            "allowable_span_d": allowable,
            "basic_ratio": limit,
            "K": K,
            "rho": rho,
            "rho_0": rho_0,
            "F3": F3,
        }


def design_flexure_T(
    code: str, M: float, b_eff: float, b_w: float, h_f: float, d: float,
    h: float, f_c: float, f_y: float, d_prime: float = 0.0,
) -> Dict[str, float | str]:
    """Rectangular-stress-block flexure for a T-section in sagging bending.

    The neutral axis is first assumed within the flange; if it falls below
    the flange, the full T-section equilibrium is solved. Hogging bending
    should still use the rectangular web section.
    """
    for name, value in (("b_eff", b_eff), ("b_w", b_w), ("h_f", h_f), ("d", d), ("h", h)):
        _require_positive(name, value)
    if b_eff < b_w:
        raise ValueError("Effective flange width cannot be less than the web width.")
    if h_f >= d:
        raise ValueError("Flange thickness must be less than the effective depth.")

    if code == "BS8110":
        f_cd = 0.67 * f_c / 1.5
        lam = 0.9
        f_yd = 0.95 * f_y
        min_pct = 0.0032 if f_y <= 250 else 0.0018
        As_min = min_pct * b_w * h
        x_limit = 0.50 * d
    elif code == "Eurocode 2":
        if f_c > 50:
            raise ValueError("T-beam design currently supports fck <= 50 MPa.")
        f_cd = 0.85 * f_c / 1.5
        lam = 0.8
        f_yd = f_y / 1.15
        f_ctm = 0.30 * f_c ** (2.0 / 3.0)
        As_min = max(0.26 * f_ctm / f_y, 0.0013) * b_w * d
        x_limit = 0.45 * d
    else:
        raise ValueError(f"Unsupported design code: {code}")

    M_Nmm = abs(M) * 1e6
    over_reinforced = False

    # Assume the neutral axis is within the flange.
    A = f_cd * b_eff * lam ** 2 / 2.0
    B = -f_cd * b_eff * lam * d
    C = M_Nmm
    disc = B * B - 4.0 * A * C
    if disc < 0:
        raise ValueError("Section is inadequate for the applied T-beam moment.")
    x_root = (-B - math.sqrt(disc)) / (2.0 * A)

    if x_root <= h_f + 1e-9:
        x = x_root
        F_c = f_cd * b_eff * lam * x
        As_req = F_c / f_yd
        section_type = "T-beam (neutral axis in flange)"
    else:
        F_f = f_cd * (b_eff - b_w) * h_f
        A2 = f_cd * b_w * lam ** 2 / 2.0
        B2 = -f_cd * b_w * lam * d
        C2 = M_Nmm - F_f * (d - h_f / 2.0)
        disc2 = B2 * B2 - 4.0 * A2 * C2
        if disc2 < 0:
            raise ValueError("Section is inadequate for the applied T-beam moment.")
        r1 = (-B2 - math.sqrt(disc2)) / (2.0 * A2)
        r2 = (-B2 + math.sqrt(disc2)) / (2.0 * A2)
        candidates = [r for r in (r1, r2) if h_f <= r <= d / lam + 1e-9]
        if not candidates:
            raise ValueError("The T-beam neutral axis lies outside the valid range.")
        x = min(candidates)
        F_w = f_cd * b_w * lam * x
        As_req = (F_f + F_w) / f_yd
        section_type = "T-beam (neutral axis in web)"

    if x > x_limit:
        over_reinforced = True
        section_type += " — compression zone exceeds the ductility limit"

    As_req = max(As_req, As_min)
    return {
        "K": 0.0,
        "z": d - lam * x / 2.0,
        "As_req": As_req,
        "As_comp": 0.0,
        "As_min": As_min,
        "x": x,
        "section_type": section_type,
        "over_reinforced": over_reinforced,
    }


def design_flexure(code: str, **kwargs):
    if code == "BS8110":
        return BS8110.design_flexure(**kwargs)
    if code == "Eurocode 2":
        return Eurocode2.design_flexure(**kwargs)
    raise ValueError(f"Unsupported design code: {code}")


def load_factors(code: str) -> tuple[float, float]:
    if code == "BS8110":
        return BS8110.load_factors()
    if code == "Eurocode 2":
        return Eurocode2.load_factors()
    raise ValueError(f"Unsupported design code: {code}")
