from __future__ import annotations

from typing import Dict, List
import math

from core.rebar import RebarSelector
from core.results import DesignAudit, CheckStatus
from core.standards import BS8110, Eurocode2, design_flexure, load_factors


class ContinuousBeam:
    """Preliminary gravity-load continuous beam design.

    The analysis uses published coefficient-style envelopes for regular
    continuous spans. It does NOT perform a general stiffness/matrix analysis.
    Unequal spans are therefore rejected rather than silently replaced by max().
    """

    def __init__(
        self, spans: List[float], b_w: float = 200.0, h_overall: float = 450.0,
        cover: float = 25.0, gk_slab: float = 12.0, qk_slab: float = 6.0,
        wall_height: float = 2.8, wall_unit_weight: float = 18.0,
        wall_thick: float = 0.20, f_cu: float = 25.0, f_y: float = 460.0,
        f_yv: float = 250.0, code: str = "BS8110"
    ):
        if not spans or any(s <= 0 for s in spans):
            raise ValueError("spans must contain positive lengths in metres.")
        if len({round(s, 6) for s in spans}) != 1:
            raise ValueError(
                "This coefficient-based beam model supports equal spans only. "
                "Use a frame analysis model for unequal spans."
            )
        self.spans = spans
        self.num_spans = len(spans)
        self.L = spans[0]
        self.b_w, self.h, self.cover = b_w, h_overall, cover
        self.f_cu, self.f_y, self.f_yv, self.code = f_cu, f_y, f_yv, code

        self.gk_slab = gk_slab
        self.qk_slab = qk_slab
        self.gk_beam_self = (b_w / 1000) * (h_overall / 1000) * 24.0
        self.gk_wall = wall_height * wall_thick * wall_unit_weight
        self.gk_total = gk_slab + self.gk_beam_self + self.gk_wall
        self.qk_total = qk_slab
        gamma_g, gamma_q = load_factors(code)
        self.w_ult = gamma_g * self.gk_total + gamma_q * self.qk_total

        self.main_bar_dia = 16
        self.link_dia = 8
        self.d = self.h - self.cover - self.link_dia - self.main_bar_dia / 2
        if self.d <= 0:
            raise ValueError("Beam effective depth is non-positive.")

    def _analysis_envelope(self) -> tuple[float, float, float]:
        L, w = self.L, self.w_ult
        if self.num_spans == 1:
            return w * L**2 / 8, 0.0, w * L / 2
        if self.num_spans == 2:
            # Exact elastic result for two equal spans, both fully loaded,
            # with simple end supports: M_support = wL²/8,
            # M_positive,max = 9wL²/128, V_internal = 5wL/8.
            return (9.0 / 128.0) * w * L**2, (1.0 / 8.0) * w * L**2, (5.0 / 8.0) * w * L
        # BS 8110 Table 3.5 gives the governing envelope for >=3 equal
        # spans: +0.09Fl at the middle of an end span, -0.11Fl at the
        # first interior support, and 0.60F at the first interior support.
        return 0.09 * w * L**2, 0.11 * w * L**2, 0.60 * w * L

    def design_beam(self) -> Dict:
        M_span, M_support, V_support = self._analysis_envelope()

        if self.code == "BS8110":
            span_flex = design_flexure("BS8110", M_u=M_span, b=self.b_w, d=self.d, f_cu=self.f_cu, f_y=self.f_y, min_steel_h=self.h)
            supp_flex = design_flexure("BS8110", M_u=M_support, b=self.b_w, d=self.d, f_cu=self.f_cu, f_y=self.f_y, min_steel_h=self.h) if M_support else {"As_req": 0.0}
        else:
            # For EC2 the suite uses cylinder strength; fcu input is not silently treated as fck.
            f_ck = 0.8 * self.f_cu
            span_flex = design_flexure("Eurocode 2", M_Ed=M_span, b=self.b_w, d=self.d, f_ck=f_ck, f_yk=self.f_y)
            supp_flex = design_flexure("Eurocode 2", M_Ed=M_support, b=self.b_w, d=self.d, f_ck=f_ck, f_yk=self.f_y) if M_support else {"As_req": 0.0}

        span_opts = RebarSelector.select_beam_bars(span_flex["As_req"], preferred_diameters=(16, 20, 25))
        supp_opts = RebarSelector.select_beam_bars(supp_flex["As_req"], preferred_diameters=(16, 20, 25))
        span_bars = span_opts[0] if span_opts else {"description": "NO VALID STANDARD ARRANGEMENT", "As_prov": 0}
        supp_bars = supp_opts[0] if supp_opts else (
            {"description": "2Y12 nominal hanger bars", "As_prov": 226.2}
            if M_support == 0 else {"description": "NO VALID STANDARD ARRANGEMENT", "As_prov": 0}
        )

        if self.code == "BS8110":
            shear = BS8110.design_shear(
                V_support, self.b_w, self.d, self.f_cu, self.f_yv, span_bars["As_prov"]
            )
        else:
            ec2_shear = Eurocode2.design_shear(
                V_support, self.b_w, self.d, f_ck, self.f_yv, span_bars["As_prov"]
            )
            shear = {
                "status": ec2_shear["status"],
                "v": ec2_shear["v"],
                "vc": ec2_shear["vrdc"],
                "v_max": ec2_shear["v_rd_max"],
                "asv_sv_req": ec2_shear["asw_sv_req"],
                "message": ec2_shear["message"],
            }

        if shear["status"] != "FAIL" and shear.get("asv_sv_req") is not None:
            max_spacing_factor = 0.75 if self.code == "BS8110" else 0.75  # EC2 6.2.3(3) also uses 0.75d for the common case
            if shear["asv_sv_req"] > 0:
                area_two_leg = 2 * math.pi * self.link_dia**2 / 4
                raw_sv = area_two_leg / shear["asv_sv_req"]
                spacing = min(int(raw_sv // 25) * 25, int(max_spacing_factor * self.d), 250)
            else:
                spacing = min(int(max_spacing_factor * self.d), 250)
            spacing = max(spacing, 75)
            prefix = "Y" if self.code == "BS8110" else "H"
            link_schedule = f"{prefix}{self.link_dia} 2-leg links @ {spacing}mm c/c"
        else:
            link_schedule = "Shear reinforcement: NOT DETERMINED (concrete strut capacity exceeded — increase section)"

        audit = DesignAudit()
        if self.code == "BS8110" and self.num_spans >= 3 and self.qk_total > self.gk_total:
            audit.add(
                "Table 3.5 applicability", CheckStatus.WARNING,
                message="BS 8110 Table 3.5 requires characteristic imposed load not to exceed characteristic dead load for this coefficient method."
            )
        elif self.code == "BS8110" and self.num_spans == 2:
            audit.add(
                "Two-span elastic analysis", CheckStatus.PASS,
                message="Exact equal-two-span UDL solution used; not the >=3-span BS 8110 Table 3.5 coefficient case."
            )
        audit.add(
            "Flexure at span", CheckStatus.PASS if span_bars["As_prov"] >= span_flex["As_req"] else CheckStatus.FAIL,
            demand=span_flex["As_req"], capacity=span_bars["As_prov"], unit="mm²", message=span_flex["section_type"]
        )
        audit.add(
            "Flexure at support", CheckStatus.PASS if supp_bars["As_prov"] >= supp_flex["As_req"] else CheckStatus.FAIL,
            demand=supp_flex["As_req"], capacity=supp_bars["As_prov"], unit="mm²"
        )
        audit.add(
            "Shear", CheckStatus.PASS if shear["status"] == "PASS" else CheckStatus.FAIL if shear["status"] == "FAIL" else CheckStatus.NOT_CHECKED,
            demand=shear.get("v"), capacity=shear.get("v_max"), unit="N/mm²", message=shear.get("message", "")
        )

        actual_span_d = self.L * 1000 / self.d
        if self.code == "BS8110":
            basic_ratio = 26.0 if self.num_spans >= 2 else 20.0
            defl = BS8110.deflection_check(
                self.b_w, self.d, M_span, span_flex["As_req"], span_bars["As_prov"],
                self.f_y, basic_ratio=basic_ratio
            )
            deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
            audit.add(
                "Deflection (span/depth screening)",
                CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
                demand=round(actual_span_d, 2), capacity=round(defl["allowable_span_d"], 2), unit="span/d",
                message="Simplified BS 8110 3.4.6 screening check; not a full long-term deflection calculation."
            )
            allowable_span_d = round(defl["allowable_span_d"], 2)
        else:
            deflection_status = "NOT CHECKED"
            allowable_span_d = None
            audit.add(
                "Deflection (span/depth screening)", CheckStatus.NOT_CHECKED,
                demand=round(actual_span_d, 2), unit="span/d",
                message="EC2 span/effective-depth screening is not implemented in this release; use the BS 8110 screening check or a full deflection calculation."
            )

        # Keep Gk/Qk separate in the result for downstream load takedown.
        # Keep service reactions separate for the load takedown.
        if self.num_spans == 1:
            reaction_coeff = 0.5
            reaction_to_column = V_support
        elif self.num_spans == 2:
            # Central support reaction for two equal fully loaded spans is 5wL/4.
            reaction_coeff = 1.25
            reaction_to_column = V_support
        else:
            # V_support is the governing first-interior-support shear (0.60wL).
            reaction_coeff = 0.60
            reaction_to_column = V_support
        reaction_gk = reaction_coeff * self.gk_total * self.L
        reaction_qk = reaction_coeff * self.qk_total * self.L
        return {
            "analysis_method": "coefficient envelope for equal spans",
            "gk_total_kN_m": round(self.gk_total, 3),
            "qk_total_kN_m": round(self.qk_total, 3),
            "w_ult_kN_m": round(self.w_ult, 3),
            "M_span_kNm": round(M_span, 3),
            "M_support_kNm": round(M_support, 3),
            "V_support_kN": round(V_support, 3),
            "span_bars": span_bars,
            "span_flex": span_flex,
            "supp_bars": supp_bars,
            "supp_flex": supp_flex,
            "link_schedule": link_schedule,
            "shear_status": shear["status"],
            "v_stress": round(shear["v"], 4),
            "vc_stress": shear.get("vc"),
            "actual_span_d": round(actual_span_d, 2),
            "allowable_span_d": allowable_span_d,
            "deflection_status": deflection_status,
            "reaction_to_column_kN": round(reaction_to_column, 3),
            "reaction_gk_to_column_kN": round(reaction_gk, 3),
            "reaction_qk_to_column_kN": round(reaction_qk, 3),
            "audit": audit.as_dict(),
            "limitations": [
                "One span uses simple-support analysis; two equal spans use the exact elastic UDL solution; three or more equal spans use the governing BS 8110/EC2 coefficient envelope.",
                "The multi-span coefficient method requires its code applicability conditions (including approximately equal spans and, for BS 8110 Table 3.5, Qk <= Gk).",
                "Deflection is a simplified span/effective-depth screening check, not a full long-term deflection analysis.",
                "EC2 shear uses the variable strut inclination method with cot(theta)=2.5; a full theta-optimisation and detailed link curtailment are not implemented.",
            ],
        }
