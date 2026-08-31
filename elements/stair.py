import math
from typing import Dict
from core.standards import design_flexure, load_factors
from core.rebar import RebarSelector

class StairFlight:
    """
    Stair Flight and Landing Design Module benchmarked against RCC71.xls.
    Calculates slope self-weight, effective span, maximum design moment, and reinforcement.
    """

    def __init__(
        self,
        going: float = 250.0,          # Tread going / run (mm)
        rise: float = 150.0,           # Step rise (mm)
        waist: float = 150.0,          # Waist thickness (mm)
        flight_going_len: float = 2.5, # Horizontal length of going part (m)
        landing_len: float = 1.2,      # Landing span length (m)
        cover: float = 25.0,           # Concrete cover (mm)
        gk_finishes: float = 1.2,      # Finishes on stairs & landing (kN/m2)
        qk_live: float = 3.0,          # Imposed live load (kN/m2)
        f_cu: float = 25.0,            # Concrete cube strength (N/mm2)
        f_y: float = 460.0,            # Rebar yield strength (N/mm2)
        code: str = "BS8110"
    ):
        for name, value in (("going", going), ("rise", rise), ("waist", waist),
                            ("flight_going_len", flight_going_len), ("landing_len", landing_len),
                            ("cover", cover), ("gk_finishes", gk_finishes), ("qk_live", qk_live),
                            ("f_cu", f_cu), ("f_y", f_y)):
            if value <= 0:
                raise ValueError(f"{name} must be > 0.")
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
        self.bar_dia = 12

        # Effective depth d
        self.d = self.waist - self.cover - (self.bar_dia / 2.0)

        # Slope geometry
        self.slope_hypotenuse = math.sqrt(going**2 + rise**2)
        self.slope_factor = self.slope_hypotenuse / going

        # Dead loads per horizontal square meter (kN/m2)
        # 1. Waist slab dead load on slope converted to plan area: (waist/1000) * 24 * slope_factor
        waist_sw = (self.waist / 1000.0) * 24.0 * self.slope_factor
        # 2. Average triangular steps weight: 0.5 * (rise/1000) * 24
        steps_sw = 0.5 * (self.rise / 1000.0) * 24.0
        self.flight_gk = waist_sw + steps_sw + self.gk_fin

        # Landing dead load per m2
        self.landing_gk = (self.waist / 1000.0) * 24.0 + self.gk_fin

        gamma_g, gamma_q = load_factors(self.code)
        self.n_flight = gamma_g * self.flight_gk + gamma_q * self.qk
        self.n_landing = gamma_g * self.landing_gk + gamma_q * self.qk

    def design_stair(self) -> Dict:
        """Calculates span moment, main bottom rebar, and transverse distribution steel."""
        L_eff = self.l_flight + self.l_landing  # Total effective span (m)
        
        # Weighted average ultimate load per linear meter (1m strip)
        total_load = (self.n_landing * self.l_landing) + (self.n_flight * self.l_flight)
        w_avg = total_load / L_eff

        # Maximum design bending moment M_u = w * L^2 / 8 (kNm/m)
        M_u = (w_avg * (L_eff ** 2)) / 8.0

        # Main tension rebar design using the selected resistance model.
        if self.code == "BS8110":
            flex_res = design_flexure("BS8110", M_u=M_u, b=1000, d=self.d, f_cu=self.f_cu, f_y=self.f_y)
        else:
            flex_res = design_flexure("Eurocode 2", M_Ed=M_u, b=1000, d=self.d, f_ck=0.8*self.f_cu, f_yk=self.f_y)
        main_rebar = RebarSelector.select_slab_spacing(flex_res["As_req"], bar_dia=self.bar_dia)

        # Transverse distribution rebar (0.13% minimum steel)
        As_dist_min = 0.0013 * 1000 * self.waist
        dist_rebar = RebarSelector.select_slab_spacing(As_dist_min, bar_dia=10, max_spacing=250)

        # Deflection check (BS 8110 Table 3.9 basic ratio = 20.0 for simply supported stairs)
        basic_span_d = 20.0
        M_bd2 = (M_u * 1e6) / (1000 * (self.d ** 2))
        fs = (2.0 / 3.0) * self.f_y * (flex_res["As_req"] / main_rebar["As_prov"])
        mf = min(2.0, 0.55 + (477.0 - fs) / (120.0 * (0.9 + M_bd2)))
        allowable_span_d = basic_span_d * mf
        actual_span_d = (L_eff * 1000.0) / self.d
        deflection_status = "PASS" if actual_span_d <= allowable_span_d else "FAIL (Increase waist)"

        # End reactions to pass to landing beam (RCC41)
        # R_support = total_load / 2 (kN per meter stair width)
        reaction_to_beam = round(total_load / 2.0, 2)

        return {
            "L_eff_m": round(L_eff, 2),
            "n_flight_kpa": round(self.n_flight, 2),
            "n_landing_kpa": round(self.n_landing, 2),
            "M_u_kNm": round(M_u, 2),
            "main_rebar": main_rebar,
            "dist_rebar": dist_rebar,
            "actual_span_d": round(actual_span_d, 1),
            "allowable_span_d": round(allowable_span_d, 1),
            "deflection_status": deflection_status,
            "reaction_to_beam_kN_m": reaction_to_beam,
            "limitations": [
                "The current model assumes a simply supported equivalent span made from flight and landing lengths; actual stair support conditions must be specified for final design.",
                "The reported span/depth result is a simplified screening check, not a full long-term deflection calculation.",
                "No torsion, diaphragm, landing-to-flight joint or support detailing design is generated."
            ]
        }