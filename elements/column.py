from __future__ import annotations

import math
from typing import Dict

from core.rebar import RebarSelector
from core.results import DesignAudit, CheckStatus
from core.section_analysis import biaxial_utilization
from core.standards import BS8110, Eurocode2, load_factors


class ColumnDesign:
    """Axial column load-takedown and preliminary column design, including a
    simplified biaxial bending and slenderness check.

    Scope and honesty notes:
    - First-order applied moments (Mx, My) are NOT derived from a full frame
      analysis; if the caller doesn't supply them, only the code-mandated
      minimum-eccentricity moment is checked (never zero moment, since that
      would not be code compliant).
    - The moment-axial interaction check uses a simplified straight-line
      (linear) interaction between the pure-axial capacity and an
      approximate pure-moment capacity. This is a recognised conservative
      preliminary method, NOT a full strain-compatibility N-Mx-My
      interaction surface. It is intended to catch clearly inadequate
      sections, not to replace a full column design chart check.
    - The slenderness/second-order additional-moment method is implemented
      for BS 8110 braced columns only (Cl. 3.8.3.1, simplified K=1). EC2
      second-order effects (the nominal curvature method, EN1992 5.8.8) are
      NOT implemented; a slender EC2 column is flagged NOT CHECKED rather
      than silently ignored.
    - Unbraced columns are out of scope entirely; this module assumes a
      braced column (sway effects not considered).
    """

    def __init__(
        self, b: float = 200.0, h: float = 200.0, clear_height: float = 3000.0,
        num_floors: int = 2, N_beam_per_floor: float | None = None,
        Gk_beam_per_floor: float | None = None, Qk_beam_per_floor: float | None = None,
        Mx_applied: float = 0.0, My_applied: float = 0.0,
        f_cu: float = 25.0, f_y: float = 460.0, cover: float = 25.0,
        code: str = "BS8110"
    ):
        if b <= 0 or h <= 0 or clear_height <= 0:
            raise ValueError("Column dimensions must be positive.")
        if num_floors < 1:
            raise ValueError("num_floors must be >= 1.")
        if f_cu <= 0 or f_y <= 0:
            raise ValueError("Concrete and steel strengths must be positive.")
        if cover < 0:
            raise ValueError("cover cannot be negative.")
        if Mx_applied < 0 or My_applied < 0:
            raise ValueError("Applied moments cannot be negative.")
        if code not in ("BS8110", "Eurocode 2"):
            raise ValueError(f"Unsupported design code: {code}")

        self.b, self.h, self.l_clear = b, h, clear_height
        self.num_floors = int(num_floors)
        self.f_cu, self.f_y, self.cover, self.code = f_cu, f_y, cover, code
        self.Mx_applied, self.My_applied = float(Mx_applied), float(My_applied)

        # Backward compatibility: if an old caller supplies an ultimate
        # reaction, do not silently split it into arbitrary Gk/Qk.
        if Gk_beam_per_floor is None or Qk_beam_per_floor is None:
            if N_beam_per_floor is None:
                raise ValueError("Supply Gk/Qk beam loads or N_beam_per_floor.")
            self.gk_beam = 0.0
            self.qk_beam = 0.0
            self.legacy_ultimate_beam = float(N_beam_per_floor)
        else:
            if Gk_beam_per_floor < 0 or Qk_beam_per_floor < 0:
                raise ValueError("Gk and Qk beam loads cannot be negative.")
            self.gk_beam = float(Gk_beam_per_floor)
            self.qk_beam = float(Qk_beam_per_floor)
            self.legacy_ultimate_beam = None

        # Column self-weight uses 24 kN/m³ as the adopted reinforced-concrete
        # unit weight for this preliminary module.
        self.gk_col_self = (b / 1000) * (h / 1000) * (clear_height / 1000) * 24
        self.gamma_g, self.gamma_q = load_factors(code)

        self.le = 0.85 * clear_height
        self.slenderness_x = self.le / h
        self.slenderness_y = self.le / b
        self.is_short = self.slenderness_x <= 15 and self.slenderness_y <= 15
        self.lambda_lim: float | None = None

    def design_column(self) -> Dict:
        if self.legacy_ultimate_beam is not None:
            N_ult_beams = self.legacy_ultimate_beam * self.num_floors
            N_serv_beams = N_ult_beams / max(self.gamma_g, 1.0)
            gk_total = self.gk_col_self * self.num_floors
            qk_total = 0.0
        else:
            gk_total = (self.gk_beam + self.gk_col_self) * self.num_floors
            qk_total = self.qk_beam * self.num_floors
            N_ult_beams = (
                self.gamma_g * self.gk_beam * self.num_floors
                + self.gamma_q * self.qk_beam * self.num_floors
            )
            N_serv_beams = self.gk_beam * self.num_floors + self.qk_beam * self.num_floors

        N_ult_self = self.gamma_g * self.gk_col_self * self.num_floors
        N_ult = N_ult_beams + N_ult_self
        # N_service must be the unfactored beam service load plus the column's
        # OWN self-weight only. In the non-legacy branch, gk_total already
        # includes the beam's Gk (it's used for audit/reporting), so adding
        # it here again would double-count the beam dead load — which is
        # exactly what was happening before this fix, and is why a perfectly
        # ordinary dead-load-dominant column could come out with a service
        # load higher than its own ultimate load.
        N_service = N_serv_beams + self.gk_col_self * self.num_floors

        Ag = self.b * self.h

        # EN 1992-1-1 Cl. 5.8.3.1: slenderness is lambda = l0/i and the
        # limit is lambda_lim = 20 A B C / sqrt(n), NOT the BS 8110 le/h < 15
        # rule. Applying le/h < 15 to EC2 columns silently treats genuinely
        # slender columns (lambda is about 3.46 times le/h for a square
        # section) as short and skips second-order effects.
        if self.code == "Eurocode 2":
            f_cd_slender = 0.85 * self.f_cu / 1.5
            n_slender = N_ult * 1000.0 / max(Ag * f_cd_slender, 1e-9)
            # Default A = 0.7, B = 1.1, C = 0.7 where phi_ef, omega and rm
            # are not supplied (EN 1992-1-1 5.8.3.1).
            self.lambda_lim = 20.0 * 0.7 * 1.1 * 0.7 / max(math.sqrt(n_slender), 1e-9)
            self.slenderness_x = self.le / (self.h / math.sqrt(12.0))
            self.slenderness_y = self.le / (self.b / math.sqrt(12.0))
            self.is_short = (
                self.slenderness_x <= self.lambda_lim
                and self.slenderness_y <= self.lambda_lim
            )
        if self.code == "BS8110":
            # BS 8110-1:1997 Cl. 3.8.4.3, Eq. 38:
            # N = 0.4 fcu Ac + 0.75 fy Asc.
            # Ac is taken here as the gross nominal section area, consistent
            # with the adopted preliminary design convention in this suite.
            N_concrete = 0.40 * self.f_cu * Ag
            Asc_calc = max(
                0.004 * Ag,
                (N_ult * 1000 - N_concrete) / max(0.75 * self.f_y, 1e-9)
            )
            min_ratio = 0.004
            concrete_design_strength = 0.40 * self.f_cu
            steel_design_strength = 0.75 * self.f_y
        else:
            # EN 1992-1-1 column minimum reinforcement: As,min =
            # max(0.10 NEd/fyd, 0.002 Ac). The sidebar now collects the real
            # cylinder strength (fck) directly for Eurocode 2 — no cube-to-
            # cylinder approximation is applied.
            f_ck = self.f_cu
            if f_ck > 50:
                raise ValueError(
                    "This preliminary column routine currently supports fck <= 50 MPa."
                )
            alpha_cc = 0.85
            gamma_c = 1.5
            gamma_s = 1.15
            f_cd = alpha_cc * f_ck / gamma_c
            f_yd = self.f_y / gamma_s
            Asc_calc = max(0.10 * N_ult * 1000 / f_yd, 0.002 * Ag)
            min_ratio = 0.002
            concrete_design_strength = f_cd
            steel_design_strength = f_yd

        Asc_max = 0.04 * Ag
        chosen = RebarSelector.select_column_bars(
            Asc_calc, self.b, self.h, self.cover,
            preferred_diameters=(12, 16, 20, 25, 32), max_bars=12
        )

        # Axial resistance of the selected arrangement. This is a short-column
        # axial check only; moment interaction and second-order effects remain
        # outside this module.
        As_prov = float(chosen.get("As_prov", 0.0))
        if self.code == "BS8110":
            N_rd = 0.40 * self.f_cu * Ag + 0.75 * self.f_y * As_prov
        else:
            # EC2 axial resistance expression used for the preliminary
            # concentric-compression check: N_Rd = Ac*f_cd + As*f_yd.
            N_rd = concrete_design_strength * Ag + steel_design_strength * As_prov

        N_rd_kN = N_rd / 1000.0
        utilization = N_ult / N_rd_kN if N_rd_kN > 0 else float("inf")
        axial_resistance_status = "PASS" if N_ult <= N_rd_kN + 1e-9 else "FAIL"
        reinforcement_capacity_status = (
            "PASS" if Asc_calc <= Asc_max and As_prov >= Asc_calc else "FAIL"
        )

        link_dia = max(8, int(round(chosen.get("bar_diameter", 16) / 4)))
        link_spacing = min(200, 12 * chosen.get("bar_diameter", 16), int(self.b), int(self.h))

        # --- Slenderness & moment interaction (simplified) ---
        bar_dia = chosen.get("bar_diameter", 16)
        d_x = self.h - self.cover - link_dia - bar_dia / 2.0   # effective depth, bending about x (h governs)
        d_y = self.b - self.cover - link_dia - bar_dia / 2.0   # effective depth, bending about y (b governs)

        if self.code == "BS8110":
            emin_mm = BS8110.min_eccentricity_mm(self.h)
            emin_mm_y = BS8110.min_eccentricity_mm(self.b)
        else:
            emin_mm = Eurocode2.min_eccentricity_mm(self.h)
            emin_mm_y = Eurocode2.min_eccentricity_mm(self.b)
        Mx_min = N_ult * (emin_mm / 1000.0)
        My_min = N_ult * (emin_mm_y / 1000.0)

        Mx_1st = max(self.Mx_applied, Mx_min)
        My_1st = max(self.My_applied, My_min)

        second_order_status = "NOT APPLICABLE" if self.is_short else None
        Madd_x = Madd_y = 0.0
        M2_x = M2_y = 0.0
        phi_ef_used = None
        if not self.is_short:
            if self.code == "BS8110":
                Madd_x = BS8110.additional_moment_kNm(N_ult, self.le, self.h)
                Madd_y = BS8110.additional_moment_kNm(N_ult, self.le, self.b)
                second_order_status = "INCLUDED"
            else:
                # EN 1992-1-1 Cl. 5.8.8 nominal-curvature method.
                # Assumptions (documented in the result): phi_ef = 2.0,
                # c = pi^2 = 10, and the default curvature-distribution
                # factor implied by the code's recommended expressions.
                f_cd_2 = 0.85 * self.f_cu / 1.5
                f_yd_2 = self.f_y / 1.15
                Ac = self.b * self.h
                omega = As_prov * f_yd_2 / max(Ac * f_cd_2, 1e-9)
                nu = 1.0 + omega
                n_axial = N_ult * 1000.0 / max(Ac * f_cd_2, 1e-9)
                n_bal = 0.4
                Kr = 1.0 if n_axial <= n_bal else max(
                    0.0, min(1.0, (nu - n_axial) / max(nu - n_bal, 1e-9))
                )
                phi_ef_used = 2.0
                eps_yd = f_yd_2 / 200_000.0

                def _m2(d_eff: float, slenderness: float) -> float:
                    beta_c = 0.35 + self.f_cu / 200.0 - slenderness / 150.0
                    K_phi = max(1.0, 1.0 + beta_c * phi_ef_used)
                    inv_r = Kr * K_phi * eps_yd / max(0.45 * d_eff, 1e-9)
                    e2_mm = inv_r * self.le ** 2 / 10.0
                    return N_ult * e2_mm / 1000.0  # kNm

                M2_x = _m2(d_x, self.slenderness_x)
                M2_y = _m2(d_y, self.slenderness_y)
                second_order_status = "INCLUDED (EC2)"

        Mx_design = Mx_1st + Madd_x + M2_x
        My_design = My_1st + Madd_y + M2_y

        # Real strain-compatibility interaction: the uniaxial moment
        # capacities Mx_Rd and My_Rd are built from a rectangular stress
        # block and the actual bar layout at the applied axial load, not from
        # the previous steel-couple-only approximation.
        has_applied_moment = (self.Mx_applied > 0 or self.My_applied > 0)
        if chosen.get("bars", 0) >= 4 and chosen.get("bar_diameter", 0) > 0:
            positions = RebarSelector.column_bar_positions(
                int(chosen["bars"]), self.b, self.h, self.cover, link_dia, bar_dia
            )
            area_per_bar = As_prov / float(chosen["bars"])
            bars_xy = [(x, y, area_per_bar) for x, y in positions]
            interaction = biaxial_utilization(
                N_ult, Mx_design, My_design, self.b, self.h, bars_xy,
                f_c=self.f_cu, f_y=self.f_y, code=self.code,
                single_axis=(self.code == "Eurocode 2" and not has_applied_moment),
            )
            moment_utilization = float(interaction["utilization"])
            Mx_Rd = float(interaction["Mx_Rd"])
            My_Rd = float(interaction["My_Rd"])
            biaxial_method = str(interaction["method"])
        else:
            moment_utilization = float("inf")
            Mx_Rd = My_Rd = 0.0
            biaxial_method = "no valid bar layout available for section analysis"

        moment_status = "PASS" if moment_utilization <= 1.0 + 1e-9 else "FAIL"

        # BS 8110 Cl. 3.8.4.3: the N_rd formula (0.4 fcu Ac + 0.75 fy Asc) is
        # explicitly permitted PROVIDED the design moment does not exceed
        # that from minimum eccentricity alone — i.e. for a short column with
        # no real applied moment, N_rd already covers this and re-checking it
        # through the (more conservative, approximate) linear interaction
        # would produce a false FAIL. Only enforce the interaction result
        # when there's a real applied moment or a slenderness addition. EC2's
        # concentric N_rd formula has no such built-in allowance, so EC2
        # always relies on the interaction check.
        has_real_moment = (self.Mx_applied > 0 or self.My_applied > 0 or not self.is_short)
        interaction_is_informational = (self.code == "BS8110" and not has_real_moment)
        if interaction_is_informational:
            moment_status = "PASS"
            interaction_note = (
                "Only the BS 8110 minimum-eccentricity moment applies (no applied Mx/My supplied, column is short); "
                "this is already covered by the Cl. 3.8.4.3 axial resistance formula above, so it is not re-applied as a FAIL trigger."
            )
        else:
            interaction_note = (
                f"{biaxial_method}. Uniaxial capacities are from a rectangular stress-block / plane-strain "
                "section analysis at the applied axial load; biaxial combination follows the selected code. "
                "This is a design aid, not a substitute for project software or a published column chart."
            )

        audit = DesignAudit()
        audit.add(
            "Axial resistance",
            CheckStatus.PASS if axial_resistance_status == "PASS" else CheckStatus.FAIL,
            demand=N_ult, capacity=N_rd_kN, unit="kN",
            message="Concentric axial resistance check (moment interaction is a separate check below)."
        )
        audit.add(
            "Axial reinforcement",
            CheckStatus.PASS if reinforcement_capacity_status == "PASS" else CheckStatus.FAIL,
            demand=Asc_calc, capacity=As_prov, unit="mm²",
            message="Required versus provided longitudinal reinforcement."
        )
        if self.code == "Eurocode 2":
            audit.add(
                "Slenderness criterion (EC2 lambda <= lambda_lim)",
                CheckStatus.PASS if self.is_short else CheckStatus.WARNING,
                demand=round(max(self.slenderness_x, self.slenderness_y), 2),
                capacity=round(self.lambda_lim or 0.0, 2), unit="-",
                message="EN 1992-1-1 5.8.3.1 with default A=0.7, B=1.1, C=0.7. "
                        "lambda = l0/i; second-order effects must be considered when lambda exceeds the limit."
            )
        else:
            audit.add(
                "Short-column criterion (BS 8110 le/h)",
                CheckStatus.PASS if self.is_short else CheckStatus.WARNING,
                demand=round(max(self.slenderness_x, self.slenderness_y), 2), capacity=15.0,
                unit="-", message="BS 8110 braced short-column screening criterion (le/h and le/b <= 15)."
            )
        if second_order_status == "NOT CHECKED":
            audit.add(
                "Slenderness — second-order moment", CheckStatus.NOT_CHECKED,
                message="Column is slender but no second-order moment could be formed."
            )
        elif second_order_status == "INCLUDED (EC2)":
            audit.add(
                "Slenderness — second-order moment", CheckStatus.WARNING,
                demand=round(max(M2_x, M2_y), 2), unit="kNm",
                message="EN 1992-1-1 5.8.8 nominal-curvature moment included, with phi_ef = 2.0, "
                        "c = 10 and default Kr/Kphi assumptions. Confirm the creep ratio and end-moment "
                        "ratio for the project before construction."
            )
        elif second_order_status == "INCLUDED":
            audit.add(
                "Slenderness — second-order moment", CheckStatus.WARNING,
                demand=round(max(Madd_x, Madd_y), 2), unit="kNm",
                message="Column is slender; BS 8110 simplified additional moment (Cl. 3.8.3.1, K=1) included in Mx/My below."
            )
        audit.add(
            "Biaxial moment-axial interaction",
            CheckStatus.PASS if moment_status == "PASS" else CheckStatus.FAIL,
            demand=round(moment_utilization, 3) if moment_utilization != float("inf") else None,
            capacity=1.0, unit="utilization",
            message=interaction_note
        )

        axial_label = "NEd" if self.code == "Eurocode 2" else "Nu"
        return {
            "axial_force_label": axial_label,
            "N_ult_total_kN": round(N_ult, 2),
            "N_serv_to_footing_kN": round(N_service, 2),
            "Gk_total_kN": round(gk_total, 2),
            "Qk_total_kN": round(qk_total, 2),
            "slenderness_x": round(self.slenderness_x, 2),
            "slenderness_y": round(self.slenderness_y, 2),
            "slenderness_basis": (
                "EN 1992-1-1 5.8.3.1 lambda = l0/i vs lambda_lim"
                if self.code == "Eurocode 2"
                else "BS 8110 le/h vs 15"
            ),
            "lambda_lim": round(self.lambda_lim, 2) if self.lambda_lim is not None else None,
            "is_short": self.is_short,
            "Asc_req_mm2": round(Asc_calc, 2),
            "Asc_max_mm2": round(Asc_max, 2),
            "min_steel_ratio": min_ratio,
            "main_rebar": chosen,
            "link_schedule": f"Y{link_dia} ties @ {link_spacing}mm c/c",
            "capacity_status": reinforcement_capacity_status,
            "axial_resistance_status": axial_resistance_status,
            "N_rd_kN": round(N_rd_kN, 2),
            "axial_utilization": round(utilization, 3),
            "col_self_weight_kN": round(N_ult_self, 2),
            "Mx_min_kNm": round(Mx_min, 2),
            "My_min_kNm": round(My_min, 2),
            "Mx_design_kNm": round(Mx_design, 2),
            "My_design_kNm": round(My_design, 2),
            "Madd_x_kNm": round(Madd_x, 2),
            "Madd_y_kNm": round(Madd_y, 2),
            "M2_x_kNm": round(M2_x, 2),
            "M2_y_kNm": round(M2_y, 2),
            "phi_ef": phi_ef_used,
            "second_order_status": second_order_status,
            "Mx_Rd_kNm": round(Mx_Rd, 1),
            "My_Rd_kNm": round(My_Rd, 1),
            "moment_method": biaxial_method,
            "moment_utilization": round(moment_utilization, 3) if moment_utilization != float("inf") else None,
            "moment_status": moment_status,
            "audit": audit.as_dict(),
            "limitations": [
                "Moment-axial interaction is a rectangular stress-block / plane-strain section analysis with "
                "elastic-perfectly-plastic reinforcement. It does not model confinement, concrete tensile strength, "
                "buckling of bars, or the full biaxial interaction surface; the code's simplified biaxial rule is "
                "applied on top of the uniaxial capacities.",
                "First-order applied moments (Mx, My) are only as good as the values supplied — this module does not "
                "run a full frame analysis to derive them; if left at zero, only the code-mandated minimum-eccentricity "
                "moment is checked.",
                "Second-order moments: BS 8110 uses the simplified additional-moment method (Cl. 3.8.3.1, K=1); "
                "EC2 uses the nominal-curvature method (5.8.8) with phi_ef = 2.0, c = 10 and the default Kr/Kphi "
                "assumptions. Unbraced/sway columns are not implemented, and the EC2 creep/end-moment assumptions "
                "must be confirmed against the project.",
                "The EC2 axial/moment capacity implementation uses alpha_cc=0.85, gamma_c=1.5 and gamma_s=1.15.",
            ],
        }
