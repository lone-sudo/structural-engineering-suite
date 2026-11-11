from __future__ import annotations

import math
from typing import Dict, Tuple

from core.rebar import RebarSelector
from core.results import DesignAudit, CheckStatus
from core.standards import BS8110, Eurocode2


class PadFooting:
    """Isolated pad footing design with explicit service/ultimate load states."""

    def __init__(
        self, N_service: float, N_ultimate: float, col_cx: float, col_cy: float,
        q_allowable: float, h_overall: float = 450, cover: float = 50,
        f_cu: float = 25.0, f_y: float = 460.0, code: str = "BS8110"
    ):
        for name, value in (("N_service", N_service), ("N_ultimate", N_ultimate),
                            ("col_cx", col_cx), ("col_cy", col_cy), ("q_allowable", q_allowable)):
            if value <= 0:
                raise ValueError(f"{name} must be > 0.")
        self.N_serv, self.N_ult = N_service, N_ultimate
        self.cx, self.cy = col_cx, col_cy
        self.qa, self.h = q_allowable, h_overall
        # BS 8110 3.3.1.4: concrete cast against an adequate blinding should
        # have at least 40 mm cover; a buried pad is normally detailed with
        # 50 mm or more. Do not let the global 25 mm superstructure cover
        # silently reduce the footing effective depth.
        self.cover = max(float(cover), 50.0)
        self.f_cu, self.f_y, self.code = f_cu, f_y, code
        self.main_bar_dia = 12
        self.d = h_overall - cover - self.main_bar_dia / 2
        if self.d <= 0:
            raise ValueError("Footing effective depth is non-positive.")

    def _self_weight(self, L: float, B: float) -> float:
        return L * B * (self.h / 1000) * 24.0

    def size_plan_dimensions(self) -> Tuple[float, float, float]:
        # Service bearing includes a 10% allowance for footing self-weight only
        # as a sizing aid; final bearing is then recalculated explicitly.
        side = math.sqrt((self.N_serv * 1.10) / self.qa)
        L = max(0.8, math.ceil(side * 10) / 10)
        B = L
        q_service = (self.N_serv + self._self_weight(L, B)) / (L * B)
        return L, B, q_service

    def _ec2_shear_capacity(self, As_prov_per_m: float, d_mm: float) -> float:
        # Sidebar collects the real cylinder strength (fck) directly for EC2.
        fck = self.f_cu
        gamma_c = 1.5
        k = min(2.0, 1 + math.sqrt(200 / d_mm))
        rho = min(0.02, As_prov_per_m / (1000 * d_mm))
        CRdc = 0.18 / gamma_c
        v_rdc = CRdc * k * (100 * rho * fck) ** (1 / 3)
        v_min = 0.035 * k ** 1.5 * math.sqrt(fck)
        return max(v_rdc, v_min)

    def design_reinforcement_and_shear(self, L: float, B: float) -> Dict:
        if L <= self.cx / 1000 or B <= self.cy / 1000:
            raise ValueError("Footing plan dimensions must exceed column dimensions.")

        area = L * B
        footing_gk = self._self_weight(L, B)
        gamma_g = 1.4 if self.code == "BS8110" else 1.35
        q_service = (self.N_serv + footing_gk) / area
        N_ult_total = self.N_ult + gamma_g * footing_gk
        q_u = N_ult_total / area

        projection_x = (L - self.cx / 1000) / 2
        projection_y = (B - self.cy / 1000) / 2
        # The same bottom mat is used in both directions. Design it for the
        # larger cantilever projection so a rectangular pad (e.g. one taken
        # from a drawing) cannot be under-reinforced in the other direction.
        projection = max(projection_x, projection_y)
        M_per_m = q_u * projection**2 / 2

        if self.code == "BS8110":
            flex = BS8110.design_flexure(M_per_m, 1000, self.d, self.f_cu, self.f_y, min_steel_h=self.h)
        else:
            flex = Eurocode2.design_flexure(
                M_per_m, 1000, self.d, self.f_cu, self.f_y
            )
        rebar = RebarSelector.select_slab_spacing(
            flex["As_req"], self.main_bar_dia, max_spacing=300, max_bar_dia=20
        )

        # One-way shear at d from the column face, in the governing direction.
        x_crit = projection - self.d / 1000
        Vu_1way = max(0.0, q_u * x_crit)  # kN per metre width
        v_1way = Vu_1way * 1000 / (1000 * self.d)

        # Punching perimeter: 1.5d for adopted BS screening, 2d for EC2.
        offset = 1.5 * self.d / 1000 if self.code == "BS8110" else 2.0 * self.d / 1000
        cx_m, cy_m = self.cx / 1000, self.cy / 1000
        u1 = 2 * ((cx_m + 2 * offset) + (cy_m + 2 * offset))
        inside_area = (cx_m + 2 * offset) * (cy_m + 2 * offset)
        Vu_punch = max(0.0, N_ult_total - q_u * inside_area)
        v_punch = Vu_punch * 1000 / (u1 * 1000 * self.d)

        audit = DesignAudit()
        audit.add(
            "Service bearing pressure", CheckStatus.PASS if q_service <= self.qa else CheckStatus.FAIL,
            demand=q_service, capacity=self.qa, unit="kN/m²"
        )
        audit.add(
            "Flexural reinforcement", CheckStatus.PASS if rebar["As_prov"] >= flex["As_req"] else CheckStatus.FAIL,
            demand=flex["As_req"], capacity=rebar["As_prov"], unit="mm²/m"
        )

        if self.code == "Eurocode 2":
            vrdc = self._ec2_shear_capacity(rebar["As_prov"], self.d)
            audit.add(
                "Punching shear", CheckStatus.PASS if v_punch <= vrdc else CheckStatus.FAIL,
                demand=round(v_punch, 4), capacity=round(vrdc, 4), unit="N/mm²",
                message="EN 1992-1-1 6.4.4 at the 2d control perimeter, unreinforced concrete."
            )
            # A pad footing is not detailed with shear links. The check must
            # therefore be v_Ed <= v_Rd,c, not "links can be provided".
            audit.add(
                "One-way shear (unreinforced)", CheckStatus.PASS if v_1way <= vrdc else CheckStatus.FAIL,
                demand=round(v_1way, 4), capacity=round(vrdc, 4), unit="N/mm²",
                message="EN 1992-1-1 6.2.2 v_Rd,c; no shear reinforcement is assumed in the footing."
            )
        else:
            vc_punch = BS8110.concrete_shear_stress(1000, self.d, self.f_cu, rebar["As_prov"])
            audit.add(
                "Punching shear (perimeter 1.5d screening)",
                CheckStatus.PASS if v_punch <= vc_punch else CheckStatus.FAIL,
                demand=round(v_punch, 4), capacity=round(vc_punch, 4), unit="N/mm²",
                message="Screening check at the 1.5d critical perimeter using the BS 8110 Table 3.8 vc expression "
                        "(same basis as beam shear); it does not check successive perimeters at 2.25d/3.0d for "
                        "reduced link requirements, so treat a FAIL here as 'increase depth', not as a full link design."
            )
            # A pad footing normally has no shear links. Previously this used
            # design_shear(), which returns PASS as soon as links *could* be
            # designed, even when v_Ed > v_c — so the audit could display
            # PASS with demand greater than capacity. Check the concrete
            # capacity directly instead.
            vc_1way = BS8110.concrete_shear_stress(1000, self.d, self.f_cu, rebar["As_prov"])
            audit.add(
                "One-way shear (unreinforced)", CheckStatus.PASS if v_1way <= vc_1way else CheckStatus.FAIL,
                demand=round(v_1way, 4), capacity=round(vc_1way, 4), unit="N/mm²",
                message="BS 8110 Table 3.8 vc at the critical section d from the column face; "
                        "no shear reinforcement is assumed in the footing."
            )

        return {
            "L_m": round(L, 3), "B_m": round(B, 3),
            "q_service_kpa": round(q_service, 3),
            "q_u_kpa": round(q_u, 3),
            "M_u_kNm_per_m": round(M_per_m, 3),
            "As_req_mm2_m": round(flex["As_req"], 2),
            "As_min_mm2_m": round(flex.get("As_min", 0.0), 2),
            "rebar": rebar,
            "v_1way_Nmm2": round(v_1way, 4),
            "v_punch_Nmm2": round(v_punch, 4),
            "punching_perimeter_m": round(u1, 3),
            "d_eff_mm": self.d,
            "cover_mm": round(self.cover, 1),
            "self_weight_kN": round(footing_gk, 2),
            "projection_x_m": round(projection_x, 3),
            "projection_y_m": round(projection_y, 3),
            "governing_projection_m": round(projection, 3),
            "h_overall_mm": round(self.h, 1),
            "audit": audit.as_dict(),
            "limitations": [
                "No overturning, sliding, eccentric-load, settlement or soil-structure interaction check.",
                "A nominal cover of at least 50 mm is enforced for a buried pad, independent of the superstructure cover.",
                "The same bottom mat is designed for the larger cantilever projection in the two directions; a "
                "rectangular pad with materially different projections should be detailed with two separate mats.",
                "BS 8110 punching shear is a screening check at the 1.5d perimeter only; it does not evaluate reduced "
                "reinforcement at successive perimeters or a full punching shear reinforcement design.",
            ],
        }
