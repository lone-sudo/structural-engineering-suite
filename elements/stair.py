import math
from typing import Dict

from core.rebar import RebarSelector
from core.results import CheckStatus, DesignAudit
from core.serviceability import ec2_crack_width
from core.standards import BS8110, Eurocode2, design_flexure, load_factors


class StairFlight:
    """Stair flight and landing design for a simply-supported idealisation.

    The flight and landing are combined into one equivalent simply-supported
    span carrying a length-weighted average UDL. This is a common preliminary
    hand method; it is not a folded-plate or finite-element analysis of the
    stair, and it does not design the landing beams or the flight/landing
    junction.
    """

    def __init__(
        self,
        going: float = 250.0,          # Tread going / run (mm)
        rise: float = 150.0,           # Step rise (mm)
        waist: float = 175.0,          # Waist thickness (mm)
        flight_going_len: float = 2.4, # Horizontal length of going part (m)
        landing_len: float = 1.2,      # Landing span length (m)
        cover: float = 25.0,           # Concrete cover (mm)
        gk_finishes: float = 1.2,      # Finishes on stairs & landing (kN/m2)
        qk_live: float = 3.0,          # Imposed live load (kN/m2)
        f_cu: float = 25.0,            # Concrete cube strength (BS) / fck (EC2)
        f_y: float = 460.0,            # Rebar yield strength (N/mm2)
        code: str = "BS8110", psi2: float = 0.3, crack_limit: float = 0.30,
    ):
        for name, value in (("going", going), ("rise", rise), ("waist", waist),
                            ("flight_going_len", flight_going_len), ("landing_len", landing_len)):
            if value <= 0:
                raise ValueError(f"{name} must be > 0.")
        for name, value in (("gk_finishes", gk_finishes), ("qk_live", qk_live)):
            if value < 0:
                raise ValueError(f"{name} cannot be negative.")
        if cover < 0:
            raise ValueError("cover cannot be negative.")
        if f_cu <= 0 or f_y <= 0:
            raise ValueError("Concrete and steel strengths must be positive.")

        self.going = going
        self.rise = rise
        self.waist = waist
        self.l_flight = flight_going_len
        self.l_landing = landing_len
        self.cover = cover
        self.gk_fin = gk_finishes
        self.qk = qk_live
        self.f_cu = f_cu
        self.f_y = f_y
        self.code = code
        self.psi2 = psi2
        self.crack_limit = crack_limit
        self.bar_dia = 12

        self.d = self.waist - self.cover - (self.bar_dia / 2.0)
        if self.d <= 0:
            raise ValueError("Stair effective depth is non-positive; increase the waist or reduce cover.")

        # Slope geometry
        self.slope_hypotenuse = math.sqrt(going**2 + rise**2)
        self.slope_factor = self.slope_hypotenuse / going

        # Dead loads per horizontal square metre (kN/m2)
        # 1. Waist slab dead load on slope converted to plan area.
        waist_sw = (self.waist / 1000.0) * 24.0 * self.slope_factor
        # 2. Average triangular step weight over the plan projection.
        steps_sw = 0.5 * (self.rise / 1000.0) * 24.0
        self.flight_gk = waist_sw + steps_sw + self.gk_fin

        # Landing dead load per m2
        self.landing_gk = (self.waist / 1000.0) * 24.0 + self.gk_fin

        gamma_g, gamma_q = load_factors(self.code)
        self.n_flight = gamma_g * self.flight_gk + gamma_q * self.qk
        self.n_landing = gamma_g * self.landing_gk + gamma_q * self.qk
        self.gamma_g, self.gamma_q = gamma_g, gamma_q

    def design_stair(self) -> Dict:
        """Span moment, main bottom rebar, distribution steel, shear and deflection."""
        L_eff = self.l_flight + self.l_landing  # Total equivalent simply-supported span (m)

        # Length-weighted average ultimate load per linear metre (1 m strip).
        total_load = (self.n_landing * self.l_landing) + (self.n_flight * self.l_flight)
        w_avg = total_load / L_eff

        # Simply-supported design actions per metre width.
        M_u = (w_avg * (L_eff ** 2)) / 8.0
        V_u = (w_avg * L_eff) / 2.0

        if self.code == "BS8110":
            flex_res = design_flexure(
                "BS8110", M_u=M_u, b=1000, d=self.d,
                f_cu=self.f_cu, f_y=self.f_y, min_steel_h=self.waist,
            )
        else:
            flex_res = design_flexure(
                "Eurocode 2", M_Ed=M_u, b=1000, d=self.d,
                f_ck=self.f_cu, f_yk=self.f_y,
            )
        main_rebar = RebarSelector.select_slab_spacing(
            flex_res["As_req"], bar_dia=self.bar_dia, max_spacing=250, max_bar_dia=16
        )

        # Transverse distribution steel. BS 8110 Table 3.25: 0.13% of the
        # gross section for fy=460, 0.24% for fy=250.
        min_pct = 0.0024 if self.f_y <= 250.0 else 0.0013
        As_dist_min = min_pct * 1000 * self.waist
        dist_rebar = RebarSelector.select_slab_spacing(
            As_dist_min, bar_dia=10, max_spacing=250
        )

        # Shear. Stairs are normally unreinforced in shear, so compare the
        # applied stress directly with the concrete capacity.
        v_stress = V_u * 1e3 / (1000 * self.d)
        if self.code == "BS8110":
            v_c = BS8110.concrete_shear_stress(1000, self.d, self.f_cu, main_rebar["As_prov"])
            shear_status = "PASS" if v_stress <= v_c else "FAIL"
        else:
            v_c = Eurocode2.concrete_shear_capacity(1000, self.d, self.f_cu, main_rebar["As_prov"])
            shear_status = "PASS" if v_stress <= v_c else "FAIL"

        # Deflection screening (simply supported, K = 1.0).
        actual_span_d = (L_eff * 1000.0) / self.d
        if self.code == "BS8110":
            defl = BS8110.deflection_check(
                1000, self.d, M_u, flex_res["As_req"], main_rebar["As_prov"],
                self.f_y, basic_ratio=20.0,
            )
            deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
            allowable_span_d = round(defl["allowable_span_d"], 2)
            defl_note = "Simplified BS 8110 3.4.6 span/depth screening; not a full long-term deflection calculation."
        else:
            defl = Eurocode2.span_depth_limit(
                self.f_cu, flex_res["As_req"], main_rebar["As_prov"], 1000, self.d,
                K=1.0, As_comp=flex_res.get("As_comp", 0.0), f_yk=self.f_y,
            )
            deflection_status = "PASS" if actual_span_d <= defl["allowable_span_d"] else "FAIL"
            allowable_span_d = round(defl["allowable_span_d"], 2)
            defl_note = "EN 1992-1-1 7.4.2 span/depth screening; not a full long-term deflection calculation."

        # End reactions to the landing/floor beams (kN per metre stair width).
        reaction_to_beam = total_load / 2.0

        # Quasi-permanent crack width (EC2 only).
        w_qp = (
            (self.landing_gk + self.psi2 * self.qk) * self.l_landing
            + (self.flight_gk + self.psi2 * self.qk) * self.l_flight
        ) / L_eff
        M_qp = w_qp * L_eff ** 2 / 8.0
        if self.code == "Eurocode 2" and main_rebar["As_prov"] > 0:
            d_actual = self.waist - self.cover - main_rebar["bar_diameter"] / 2.0
            cw = ec2_crack_width(
                M_qp, 1000, self.waist, d_actual, main_rebar["As_prov"],
                main_rebar["bar_diameter"], self.cover, self.f_cu, self.f_y, self.crack_limit,
            )
            crack_status = cw["status"]
        else:
            cw = {"wk_mm": None, "status": "NOT CHECKED",
                  "message": "BS 8110 crack width is not implemented; only the EC2 method is available."}
            crack_status = "NOT CHECKED"

        audit = DesignAudit()
        audit.add(
            "Flexural reinforcement",
            CheckStatus.PASS if main_rebar["As_prov"] >= flex_res["As_req"] else CheckStatus.FAIL,
            demand=round(flex_res["As_req"], 1), capacity=main_rebar["As_prov"], unit="mm²/m",
            message="Main bottom steel for the equivalent simply-supported span.",
        )
        audit.add(
            "Distribution reinforcement",
            CheckStatus.PASS if dist_rebar["As_prov"] >= As_dist_min else CheckStatus.FAIL,
            demand=round(As_dist_min, 1), capacity=dist_rebar["As_prov"], unit="mm²/m",
            message="Transverse distribution steel at the code minimum percentage.",
        )
        audit.add(
            "Shear (unreinforced)",
            CheckStatus.PASS if shear_status == "PASS" else CheckStatus.FAIL,
            demand=round(v_stress, 4), capacity=round(v_c, 4), unit="N/mm²",
            message="Concrete shear capacity; increase the waist if this fails.",
        )
        audit.add(
            "Deflection (span/depth screening)",
            CheckStatus.PASS if deflection_status == "PASS" else CheckStatus.FAIL,
            demand=round(actual_span_d, 2), capacity=allowable_span_d, unit="span/d",
            message=defl_note,
        )
        audit.add(
            "Crack width (quasi-permanent)",
            CheckStatus.PASS if crack_status == "PASS"
            else CheckStatus.FAIL if crack_status == "FAIL"
            else CheckStatus.NOT_CHECKED,
            demand=round(cw["wk_mm"], 3) if cw["wk_mm"] is not None else None,
            capacity=self.crack_limit if self.code == "Eurocode 2" else None,
            unit="mm", message=cw.get("message", ""),
        )

        return {
            "analysis_method": "Length-weighted average UDL on an equivalent simply-supported span",
            "L_eff_m": round(L_eff, 2),
            "n_flight_kpa": round(self.n_flight, 2),
            "n_landing_kpa": round(self.n_landing, 2),
            "w_avg_kN_m": round(w_avg, 2),
            "M_u_kNm": round(M_u, 2),
            "V_u_kN_m": round(V_u, 2),
            "M_qp_kNm": round(M_qp, 2),
            "wk_mm": round(cw["wk_mm"], 3) if cw["wk_mm"] is not None else None,
            "crack_status": crack_status,
            "main_rebar": main_rebar,
            "dist_rebar": dist_rebar,
            "As_req_mm2_m": round(flex_res["As_req"], 1),
            "actual_span_d": round(actual_span_d, 1),
            "allowable_span_d": allowable_span_d,
            "deflection_status": deflection_status,
            "shear_status": shear_status,
            "v_stress_Nmm2": round(v_stress, 4),
            "v_capacity_Nmm2": round(v_c, 4),
            "reaction_to_beam_kN_m": round(reaction_to_beam, 2),
            "audit": audit.as_dict(),
            "limitations": [
                "The stair is idealised as a simply-supported equivalent span made from the flight and landing "
                "lengths; actual support conditions and the flight/landing junction must be designed separately.",
                "The reported span/depth result is a simplified screening check, not a full long-term deflection calculation.",
                "EC2 crack width (7.3.4) is checked under the quasi-permanent combination. BS 8110 crack width is NOT CHECKED.",
                "No torsion, diaphragm action, landing-beam design or support detailing is generated.",
            ],
        }
