from __future__ import annotations

from typing import Dict, Tuple

from core.rebar import RebarSelector
from core.results import DesignAudit, CheckStatus
from core.serviceability import ec2_crack_width
from core.standards import BS8110, Eurocode2, design_flexure, load_factors


class OneWaySlab:
    """Preliminary one-way slab strip design for a simply-supported span.

    Uses a 1 m wide strip and the selected code load factors/flexural resistance.
    This is deliberately labelled as a preliminary model: support continuity,
    redistribution, openings, vibration and full serviceability checks are not
    represented.
    """
    def __init__(self, span: float, h_slab: float = 150.0, cover: float = 25.0,
                 gk_finishes: float = 1.5, qk_live: float = 2.0,
                 f_cu: float = 25.0, f_y: float = 460.0, code: str = "BS8110",
                 psi2: float = 0.3, crack_limit: float = 0.30):
        if span <= 0 or h_slab <= 0:
            raise ValueError("Span and slab thickness must be positive.")
        if gk_finishes < 0 or qk_live < 0:
            raise ValueError("Finishes and imposed load cannot be negative.")
        self.span, self.h, self.cover = span, h_slab, cover
        self.gk_finishes, self.qk = gk_finishes, qk_live
        self.f_cu, self.f_y, self.code = f_cu, f_y, code
        self.psi2 = psi2
        self.crack_limit = crack_limit
        self.bar_dia = 10.0
        self.gk_self = h_slab / 1000 * 24.0
        self.gk_total = self.gk_self + gk_finishes
        gamma_g, gamma_q = load_factors(code)
        self.w_ult = gamma_g * self.gk_total + gamma_q * qk_live
        self.d = h_slab - cover - self.bar_dia / 2
        if self.d <= 0:
            raise ValueError("Effective slab depth is non-positive.")

    def design(self) -> Dict:
        M = self.w_ult * self.span**2 / 8.0
        V = self.w_ult * self.span / 2.0
        if self.code == "BS8110":
            flex = BS8110.design_flexure(M, 1000, self.d, self.f_cu, self.f_y, min_steel_h=self.h)
        else:
            flex = Eurocode2.design_flexure(M, 1000, self.d, self.f_cu, self.f_y)  # EC2 sidebar collects fck directly
        rebar = RebarSelector.select_slab_spacing(flex["As_req"], 10, max_spacing=250)
        audit = DesignAudit()
        audit.add("Flexural reinforcement", CheckStatus.PASS if rebar["As_prov"] >= flex["As_req"] else CheckStatus.FAIL, demand=flex["As_req"], capacity=rebar["As_prov"], unit="mm²/m")

        v_stress = V * 1e3 / (1000 * self.d)
        if self.code == "BS8110":
            vc = BS8110.concrete_shear_stress(1000, self.d, self.f_cu, rebar["As_prov"])
            shear_status = CheckStatus.PASS if v_stress <= vc else CheckStatus.FAIL
            audit.add("Shear (unreinforced slab screening)", shear_status, demand=round(v_stress, 4), capacity=round(vc, 4), unit="N/mm²",
                      message="Solid slabs are not normally provided with shear reinforcement; increase depth if this fails.")
        else:
            f_ck = self.f_cu  # EC2 sidebar collects fck directly
            vc = Eurocode2.concrete_shear_capacity(1000, self.d, f_ck, rebar["As_prov"])
            shear_status = CheckStatus.PASS if v_stress <= vc else CheckStatus.FAIL
            audit.add("Shear (unreinforced slab screening)", shear_status, demand=round(v_stress, 4), capacity=round(vc, 4), unit="N/mm²",
                      message="EN 1992-1-1 6.2.2 v_Rd,c screening; increase depth if this fails.")

        actual_span_d = self.span * 1000 / self.d
        if self.code == "BS8110":
            defl = BS8110.deflection_check(1000, self.d, M, flex["As_req"], rebar["As_prov"], self.f_y, basic_ratio=20.0)
            deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
            allowable_span_d = round(defl["allowable_span_d"], 2)
            audit.add("Deflection (span/depth screening)", CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
                      demand=round(actual_span_d, 2), capacity=allowable_span_d, unit="span/d",
                      message="Simplified BS 8110 3.4.6 screening check; not a full long-term deflection calculation.")
        else:
            defl = Eurocode2.span_depth_limit(
                self.f_cu, flex["As_req"], rebar["As_prov"], 1000, self.d,
                K=1.0, As_comp=flex.get("As_comp", 0.0), f_yk=self.f_y,
            )
            deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
            allowable_span_d = round(defl["allowable_span_d"], 2)
            audit.add("Deflection (span/depth screening)", CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
                      demand=round(actual_span_d, 2), capacity=allowable_span_d, unit="span/d",
                      message="EN 1992-1-1 7.4.2 span/depth screening; not a full long-term deflection calculation.")

        M_qp = (self.gk_total + self.psi2 * self.qk) * self.span ** 2 / 8.0
        if self.code == "Eurocode 2" and rebar["As_prov"] > 0:
            d_actual = self.h - self.cover - rebar["bar_diameter"] / 2.0
            cw = ec2_crack_width(
                M_qp, 1000, self.h, d_actual, rebar["As_prov"],
                rebar["bar_diameter"], self.cover, self.f_cu, self.f_y, self.crack_limit,
            )
            crack_status = cw["status"]
        else:
            cw = {"wk_mm": None, "status": "NOT CHECKED",
                  "message": "BS 8110 crack width is not implemented; only the EC2 method is available."}
            crack_status = "NOT CHECKED"
        audit.add(
            "Crack width (quasi-permanent)",
            CheckStatus.PASS if crack_status == "PASS" else CheckStatus.FAIL if crack_status == "FAIL" else CheckStatus.NOT_CHECKED,
            demand=round(cw["wk_mm"], 3) if cw["wk_mm"] is not None else None,
            capacity=self.crack_limit if self.code == "Eurocode 2" else None,
            unit="mm", message=cw.get("message", ""),
        )

        return {
            "analysis_method": "Simply supported 1 m strip preliminary analysis",
            "gk_self_kpa": round(self.gk_self, 3),
            "gk_finishes_kpa": round(self.gk_finishes, 3),
            "gk_total_kpa": round(self.gk_total, 3),
            "qk_kpa": round(self.qk, 3),
            "n_ult_kpa": round(self.w_ult, 3),
            "M_u_kNm_per_m": round(M, 3),
            "V_u_kN_per_m": round(V, 3),
            "As_req_mm2_m": round(flex["As_req"], 2),
            "rebar": rebar,
            "v_stress_Nmm2": round(v_stress, 4),
            "M_qp_kNm_per_m": round(M_qp, 3),
            "wk_mm": round(cw["wk_mm"], 3) if cw["wk_mm"] is not None else None,
            "sigma_s_Nmm2": round(cw.get("sigma_s", 0.0), 1),
            "crack_status": crack_status,
            "actual_span_d": round(actual_span_d, 2),
            "allowable_span_d": allowable_span_d,
            "deflection_status": deflection_status,
            "audit": audit.as_dict(),
            "limitations": [
                "Simply supported one-way strip; support continuity is not modelled.",
                "Shear and deflection are simplified screening checks (unreinforced-slab shear stress, span/effective-depth ratio), not full vibration or long-term deflection calculations.",
                "EC2 crack width (7.3.4) is checked under the quasi-permanent combination. BS 8110 crack width is NOT CHECKED.",
            ],
        }


class TwoWaySlab:
    """Two-way slab panel using a coefficient-based moment analysis.

    The moment coefficients are explicitly identified as BS 8110 Table 3.14
    analysis coefficients. EC2 selection changes load factors and section
    resistance calculations; it does not magically convert the analysis table
    into an EC2 analysis method.
    """

    # BS 8110-1:1997 Table 3.14 bending-moment coefficients.
    # Each tuple is (negative-short, positive-short, negative-long, positive-long).
    # None means the table gives no negative coefficient for that ratio/panel case.
    _RATIOS = (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.75, 2.0)
    BS_COEFFS = {
        "Interior Panel": (
            (0.031,0.037,0.042,0.046,0.050,0.053,0.059,0.063),
            (0.024,0.028,0.032,0.035,0.037,0.040,0.044,0.048),
            (0.032,)*8, (0.024,)*8),
        "One Short Edge Discontinuous": (
            (0.039,0.044,0.048,0.052,0.055,0.058,0.063,0.067),
            (0.029,0.033,0.036,0.039,0.041,0.043,0.047,0.050),
            (0.037,)*8, (0.028,)*8),
        "One Long Edge Discontinuous": (
            (0.039,0.049,0.056,0.062,0.068,0.073,0.082,0.089),
            (0.030,0.036,0.042,0.047,0.051,0.055,0.062,0.067),
            (0.037,)*8, (0.028,)*8),
        "Two Adjacent Edges Discontinuous": (
            (0.047,0.056,0.063,0.069,0.074,0.078,0.087,0.093),
            (0.036,0.042,0.047,0.051,0.055,0.059,0.065,0.070),
            (0.045,)*8, (0.034,)*8),
        "Two Short Edges Discontinuous": (
            (0.046,0.050,0.054,0.057,0.060,0.062,0.067,0.070),
            (0.034,0.038,0.040,0.043,0.045,0.047,0.050,0.053),
            (None,)*7 + (None,), (0.034,)*8),
        "Two Long Edges Discontinuous": (
            (None,)*8,
            (0.034,0.046,0.056,0.065,0.072,0.078,0.091,0.100),
            (None,)*7 + (0.045,), (0.034,)*8),
        "Three Edges Discontinuous (One Long Edge Continuous)": (
            (0.057,0.065,0.071,0.076,0.081,0.084,0.092,0.098),
            (0.043,0.048,0.053,0.057,0.060,0.063,0.069,0.074),
            (None,)*8, (0.044,)*8),
        "Three Edges Discontinuous (One Short Edge Continuous)": (
            (None,)*8,
            (0.042,0.054,0.063,0.071,0.078,0.084,0.096,0.105),
            (None,)*7 + (0.058,), (0.044,)*8),
        "Four Edges Discontinuous": (
            (None,)*8,
            (0.055,0.065,0.074,0.081,0.087,0.092,0.103,0.111),
            (None,)*8, (0.056,)*8),
    }

    def __init__(
        self, lx: float, ly: float, h_slab: float = 150.0, cover: float = 25.0,
        gk_finishes: float = 1.5, qk_live: float = 2.0, f_cu: float = 25.0,
        f_y: float = 460.0, panel_type: str = "Interior Panel",
        code: str = "BS8110", psi2: float = 0.3, crack_limit: float = 0.30,
    ):
        if lx <= 0 or ly <= 0 or h_slab <= 0:
            raise ValueError("Slab dimensions and thickness must be positive.")
        self.lx, self.ly = min(lx, ly), max(lx, ly)
        self.ratio = self.ly / self.lx
        self.h, self.cover = h_slab, cover
        self.gk_fin, self.qk = gk_finishes, qk_live
        self.f_cu, self.f_y = f_cu, f_y
        self.panel_type, self.code = panel_type, code
        self.psi2 = psi2
        self.crack_limit = crack_limit
        self.bar_dia = 10

        self.gk_self = h_slab / 1000 * 24.0
        self.gk_total = self.gk_self + gk_finishes
        gamma_g, gamma_q = load_factors(code)
        self.n_ult = gamma_g * self.gk_total + gamma_q * self.qk
        self.n_qp = self.gk_total + self.psi2 * self.qk

        self.dx = self.h - self.cover - self.bar_dia / 2
        self.dy = self.dx - self.bar_dia
        if self.dx <= 0 or self.dy <= 0:
            raise ValueError("Effective slab depth is non-positive.")

    def _interpolate_coeffs(self) -> Tuple[float, float, float, float]:
        if self.panel_type not in self.BS_COEFFS:
            raise ValueError(f"Unsupported slab panel type: {self.panel_type}")
        rows = self.BS_COEFFS[self.panel_type]
        r = min(max(self.ratio, 1.0), 2.0)

        def interp(values):
            if all(v is None for v in values):
                return 0.0
            # Table 3.14 uses a dash where a negative coefficient is not applicable.
            # If only the 2.0 ratio has a value, use it only at r=2.0; otherwise zero.
            if r < 2.0 and any(v is None for v in values):
                # Mixed None/value rows occur only where the code supplies a value at 2.0.
                valid = [(rr, vv) for rr, vv in zip(self._RATIOS, values) if vv is not None]
                if not valid:
                    return 0.0
                if len(valid) == 1:
                    return 0.0
            vals = [0.0 if v is None else float(v) for v in values]
            for i in range(len(self._RATIOS)-1):
                r1, r2 = self._RATIOS[i], self._RATIOS[i+1]
                if r1 <= r <= r2:
                    f = (r-r1)/(r2-r1)
                    return vals[i] + f*(vals[i+1]-vals[i])
            return vals[-1]

        return tuple(interp(row) for row in rows)

    def _flexure(self, M, d):
        if self.code == "BS8110":
            return design_flexure("BS8110", M_u=M, b=1000, d=d, f_cu=self.f_cu, f_y=self.f_y, min_steel_h=self.h)
        return design_flexure("Eurocode 2", M_Ed=M, b=1000, d=d, f_ck=self.f_cu, f_yk=self.f_y)  # EC2 sidebar collects fck directly

    def design_panel(self) -> Dict:
        axn, axp, ayn, ayp = self._interpolate_coeffs()
        Msx_pos = axp * self.n_ult * self.lx**2
        Msy_pos = ayp * self.n_ult * self.lx**2
        Msx_neg = axn * self.n_ult * self.lx**2
        Msy_neg = ayn * self.n_ult * self.lx**2

        sx = self._flexure(Msx_pos, self.dx)
        sy = self._flexure(Msy_pos, self.dy)
        sx_neg = self._flexure(Msx_neg, self.dx) if Msx_neg else {"As_req": 0.0}
        sy_neg = self._flexure(Msy_neg, self.dy) if Msy_neg else {"As_req": 0.0}

        sx_bar = RebarSelector.select_slab_spacing(sx["As_req"], 10, max_spacing=250)
        sy_bar = RebarSelector.select_slab_spacing(sy["As_req"], 10, max_spacing=250)
        sx_neg_bar = RebarSelector.select_slab_spacing(sx_neg["As_req"], 10, max_spacing=250)
        sy_neg_bar = RebarSelector.select_slab_spacing(sy_neg["As_req"], 10, max_spacing=250)

        audit = DesignAudit()
        for name, req, prov in (
            ("Bottom X flexure", sx["As_req"], sx_bar["As_prov"]),
            ("Bottom Y flexure", sy["As_req"], sy_bar["As_prov"]),
            ("Top X flexure", sx_neg["As_req"], sx_neg_bar["As_prov"]),
            ("Top Y flexure", sy_neg["As_req"], sy_neg_bar["As_prov"]),
        ):
            audit.add(name, CheckStatus.PASS if prov >= req else CheckStatus.FAIL,
                      demand=req, capacity=prov, unit="mm²/m")

        # This remains a screening span/depth check; no full long-term deflection analysis.
        actual_span_d = self.lx * 1000 / self.dx
        # EN 1992-1-1 7.4.2 structural-system factor K: 1.0 simply
        # supported, 1.3 end span, 1.5 interior span.
        _ec2_k_by_panel = {
            "Interior Panel": 1.5,
            "One Short Edge Discontinuous": 1.3,
            "One Long Edge Discontinuous": 1.3,
            "Two Adjacent Edges Discontinuous": 1.3,
            "Two Short Edges Discontinuous": 1.3,
            "Two Long Edges Discontinuous": 1.3,
            "Three Edges Discontinuous (One Long Edge Continuous)": 1.0,
            "Three Edges Discontinuous (One Short Edge Continuous)": 1.0,
            "Four Edges Discontinuous": 1.0,
        }
        if self.code == "BS8110":
            # BS 8110 Table 3.9's "continuous" basic ratio (26) applies whenever the
            # SHORT span (the one this check evaluates, self.dx) is continuous over
            # at least one support; only a short span that is discontinuous at BOTH
            # ends is "simply supported" (20). This depends on which specific edges
            # Table 3.14 treats as discontinuous for each panel type, not merely
            # whether the panel is literally named "Interior Panel" — the previous
            # version of this check used 20 for every non-interior panel, which is
            # unnecessarily conservative for e.g. "Two Adjacent Edges Discontinuous"
            # (verified against a real RCC94/BS8110 reference calculation: that
            # panel type correctly uses 26, not 20).
            _short_span_simply_supported_panels = {
                "Two Short Edges Discontinuous",
                "Three Edges Discontinuous (One Long Edge Continuous)",
                "Four Edges Discontinuous",
            }
            basic_ratio = 20.0 if self.panel_type in _short_span_simply_supported_panels else 26.0
            defl = BS8110.deflection_check(1000, self.dx, Msx_pos, sx["As_req"], sx_bar["As_prov"], self.f_y, basic_ratio=basic_ratio)
            deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
            allowable_span_d = round(defl["allowable_span_d"], 2)
            audit.add("Deflection (span/depth screening)", CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
                      demand=round(actual_span_d, 2), capacity=allowable_span_d, unit="span/d",
                      message="Simplified BS 8110 3.4.6 screening check on the short-span strip; not a full long-term deflection calculation.")
        else:
            k_system = _ec2_k_by_panel.get(self.panel_type, 1.0)
            defl = Eurocode2.span_depth_limit(
                self.f_cu, sx["As_req"], sx_bar["As_prov"], 1000, self.dx,
                K=k_system, As_comp=sx.get("As_comp", 0.0), f_yk=self.f_y,
            )
            deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
            allowable_span_d = round(defl["allowable_span_d"], 2)
            audit.add("Deflection (span/depth screening)", CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
                      demand=round(actual_span_d, 2), capacity=allowable_span_d, unit="span/d",
                      message="EN 1992-1-1 7.4.2 span/depth screening (K="
                              f"{k_system:g}); not a full long-term deflection calculation.")

        # Crack width under the quasi-permanent combination (EC2 only).
        M_qp_x_pos = axp * self.n_qp * self.lx ** 2
        M_qp_y_pos = ayp * self.n_qp * self.lx ** 2
        M_qp_x_neg = axn * self.n_qp * self.lx ** 2
        M_qp_y_neg = ayn * self.n_qp * self.lx ** 2
        dx_actual = self.h - self.cover - sx_bar["bar_diameter"] / 2.0
        dy_actual = self.h - self.cover - sx_bar["bar_diameter"] - sy_bar["bar_diameter"] / 2.0
        crack_results = {}
        for key, M_qp, b_bar, d_eff in (
            ("x_pos", M_qp_x_pos, sx_bar, dx_actual),
            ("y_pos", M_qp_y_pos, sy_bar, max(dy_actual, 1.0)),
            ("x_neg", M_qp_x_neg, sx_neg_bar, dx_actual),
            ("y_neg", M_qp_y_neg, sy_neg_bar, max(dy_actual, 1.0)),
        ):
            if M_qp <= 0 or b_bar["As_prov"] <= 0:
                cw = {"wk_mm": None, "status": "N/A",
                      "message": "No moment in this location — crack width not applicable."}
                stat = "N/A"
            elif self.code == "Eurocode 2":
                cw = ec2_crack_width(
                    max(0.0, M_qp), 1000, self.h, d_eff, b_bar["As_prov"],
                    b_bar["bar_diameter"], self.cover, self.f_cu, self.f_y, self.crack_limit,
                )
                stat = cw["status"]
            else:
                cw = {"wk_mm": None, "status": "NOT CHECKED",
                      "message": "BS 8110 crack width is not implemented; only the EC2 method is available."}
                stat = "NOT CHECKED"
            crack_results[key] = {"result": cw, "status": stat, "M_qp": M_qp}
            audit.add(
                f"Crack width {key.replace('_', ' ')} (quasi-permanent)",
                CheckStatus.PASS if stat == "PASS"
                else CheckStatus.FAIL if stat == "FAIL"
                else CheckStatus.NOT_APPLICABLE if stat == "N/A"
                else CheckStatus.NOT_CHECKED,
                demand=round(cw["wk_mm"], 3) if cw["wk_mm"] is not None else None,
                capacity=self.crack_limit if self.code == "Eurocode 2" else None,
                unit="mm", message=cw.get("message", ""),
            )
        _crack_statuses = [v["status"] for v in crack_results.values() if v["status"] != "N/A"]
        overall_crack_status = "FAIL" if "FAIL" in _crack_statuses else (
            "NOT CHECKED" if "NOT CHECKED" in _crack_statuses else "PASS")

        # Service and ultimate tributary line reactions are kept separate.
        gk_short = self.gk_total * self.lx / 3
        qk_short = self.qk * self.lx / 3
        gk_long = self.gk_total * self.lx / 2 * (1 - 1 / (3 * self.ratio**2))
        qk_long = self.qk * self.lx / 2 * (1 - 1 / (3 * self.ratio**2))
        gamma_g, gamma_q = load_factors(self.code)

        return {
            "analysis_method": (
                "BS 8110 Table 3.14 coefficient method"
                if self.code == "BS8110"
                else "BS 8110 Table 3.14 coefficients with EN 1992 load factors and section resistance "
                     "(no EC2-specific two-way coefficient table is implemented)"
            ),
            "gk_slab_kpa": round(self.gk_total, 3),
            "gk_self_kpa": round(self.gk_self, 3),
            "gk_finishes_kpa": round(self.gk_fin, 3),
            "qk_slab_kpa": round(self.qk, 3),
            "n_ult_kpa": round(self.n_ult, 3),
            "ratio": round(self.ratio, 3),
            "Msx_pos": round(Msx_pos, 3), "Msy_pos": round(Msy_pos, 3),
            "Msx_neg": round(Msx_neg, 3), "Msy_neg": round(Msy_neg, 3),
            "rebar_sx": sx_bar, "rebar_sy": sy_bar,
            "rebar_sx_neg": sx_neg_bar, "rebar_sy_neg": sy_neg_bar,
            "n_qp_kpa": round(self.n_qp, 3),
            "crack_status": overall_crack_status,
            "wk_x_pos_mm": round(crack_results["x_pos"]["result"]["wk_mm"], 3) if crack_results["x_pos"]["result"]["wk_mm"] is not None else None,
            "wk_y_pos_mm": round(crack_results["y_pos"]["result"]["wk_mm"], 3) if crack_results["y_pos"]["result"]["wk_mm"] is not None else None,
            "wk_x_neg_mm": round(crack_results["x_neg"]["result"]["wk_mm"], 3) if crack_results["x_neg"]["result"]["wk_mm"] is not None else None,
            "wk_y_neg_mm": round(crack_results["y_neg"]["result"]["wk_mm"], 3) if crack_results["y_neg"]["result"]["wk_mm"] is not None else None,
            "deflection_status": deflection_status,
            "actual_span_d": round(actual_span_d, 2),
            "allowable_span_d": allowable_span_d,
            "w_beam_short_gk_kN_m": round(gk_short, 3),
            "w_beam_short_qk_kN_m": round(qk_short, 3),
            "w_beam_long_gk_kN_m": round(gk_long, 3),
            "w_beam_long_qk_kN_m": round(qk_long, 3),
            "w_beam_long_kN_m": round(gamma_g*gk_long + gamma_q*qk_long, 3),
            "audit": audit.as_dict(),
            "limitations": [
                "Coefficient-based two-way slab analysis assumes the tabulated rectangular-panel method and its applicability conditions.",
                "Selecting Eurocode 2 changes the load factors and the section resistance, but the bending-moment analysis still uses the BS 8110 Table 3.14 coefficients. It is not an EC2-specific coefficient method, a finite-element analysis or an equivalent-frame analysis.",
                "Deflection is a simplified span/effective-depth screening check on the short-span strip only; not a full long-term deflection calculation.",
                "EC2 crack width (7.3.4) is checked at the four critical moment locations under the quasi-permanent combination. BS 8110 crack width is NOT CHECKED.",
                "Corner torsion detailing is not yet generated from the selected edge condition.",
                "The line loads reported for the supporting beams are moment-equivalent UDLs (not raw tributary reactions); they are appropriate for beam bending design but conservative for column load takedown.",
            ],
        }
