from __future__ import annotations

import io
import math
from typing import Dict, List

import pandas as pd

from elements.slab import TwoWaySlab
from elements.beam import ContinuousBeam
from elements.column import ColumnDesign
from elements.footing import PadFooting
from core.rebar import RebarSelector


class BuildingModel:
    """Representative-bay gravity load path: slab -> beam -> column -> footing.

    This is intentionally described as a representative bay model. It does
    not infer an entire building frame from one bay.
    """

    def __init__(
        self, bay_lx: float, bay_ly: float, num_storeys: int = 3,
        h_slab: float = 150.0, col_dim: float = 200.0,
        beam_h: float = 450.0, beam_b: float = 200.0,
        q_allowable: float = 150.0, code: str = "BS8110",
        f_cu: float = 25.0, f_y: float = 460.0,
        slab_gk_finishes: float = 1.5, slab_qk_live: float = 2.0,
        wall_height: float = 2.8, wall_unit_weight: float = 18.0, wall_thick: float = 0.20
    ):
        if bay_lx <= 0 or bay_ly <= 0:
            raise ValueError("Bay dimensions must be positive.")
        self.lx, self.ly = bay_lx, bay_ly
        self.num_storeys = int(num_storeys)
        self.h_slab, self.col_dim = h_slab, col_dim
        self.beam_h, self.beam_b = beam_h, beam_b
        self.qa, self.code = q_allowable, code
        self.f_cu, self.f_y = f_cu, f_y
        self.slab_gk_finishes = slab_gk_finishes
        self.slab_qk_live = slab_qk_live
        self.wall_height = wall_height
        self.wall_unit_weight = wall_unit_weight
        self.wall_thick = wall_thick

    def run_full_design(self) -> Dict:
        slab = TwoWaySlab(
            lx=self.lx, ly=self.ly, h_slab=self.h_slab,
            gk_finishes=self.slab_gk_finishes, qk_live=self.slab_qk_live,
            f_cu=self.f_cu, f_y=self.f_y, code=self.code
        )
        slab_res = slab.design_panel()

        # The long-beam slab tributary reaction is split into Gk/Qk BEFORE
        # applying ULS factors. This fixes the original double-factoring error.
        beam = ContinuousBeam(
            spans=[self.ly, self.ly],
            b_w=self.beam_b, h_overall=self.beam_h,
            gk_slab=slab_res["w_beam_long_gk_kN_m"],
            qk_slab=slab_res["w_beam_long_qk_kN_m"],
            wall_height=self.wall_height, wall_unit_weight=self.wall_unit_weight,
            wall_thick=self.wall_thick,
            f_cu=self.f_cu, f_y=self.f_y, code=self.code
        )
        beam_res = beam.design_beam()

        # Representative internal-column load: two framing beam reactions.
        gk_beam_to_column = 2 * beam_res["reaction_gk_to_column_kN"]
        qk_beam_to_column = 2 * beam_res["reaction_qk_to_column_kN"]

        column = ColumnDesign(
            b=self.col_dim, h=self.col_dim, num_floors=self.num_storeys,
            Gk_beam_per_floor=gk_beam_to_column,
            Qk_beam_per_floor=qk_beam_to_column,
            f_cu=self.f_cu, f_y=self.f_y, code=self.code
        )
        col_res = column.design_column()

        footing = PadFooting(
            N_service=col_res["N_serv_to_footing_kN"],
            N_ultimate=col_res["N_ult_total_kN"],
            col_cx=self.col_dim, col_cy=self.col_dim,
            q_allowable=self.qa, f_cu=self.f_cu, f_y=self.f_y, code=self.code
        )
        auto_L, auto_B, q_service = footing.size_plan_dimensions()
        footing_res = footing.design_reinforcement_and_shear(auto_L, auto_B)

        overall = {
            "overall_status": self._overall_status(
                slab_res, beam_res, col_res, footing_res
            ),
            "model_scope": "Representative internal gravity bay only",
            "axial_force_label": "NEd" if self.code == "Eurocode 2" else "Nu",
            "load_path": [
                "Slab Gk/Qk -> beam Gk/Qk",
                "Beam Gk/Qk -> representative internal column",
                f"Column cumulative Gk/Qk -> {('NEd' if self.code == 'Eurocode 2' else 'Nu')} -> footing",
            ],
        }
        return {
            "slab": slab_res,
            "beam": beam_res,
            "column": col_res,
            "footing": footing_res,
            "pad_size": (auto_L, auto_B, q_service),
            "summary": overall,
        }

    @staticmethod
    def _overall_status(*results: Dict) -> str:
        statuses = [r.get("audit", {}).get("overall_status", "NOT CHECKED") for r in results]
        if "FAIL" in statuses:
            return "FAIL"
        if "NOT CHECKED" in statuses:
            return "NOT CHECKED"
        if "WARNING" in statuses:
            return "WARNING"
        return "PASS"

    def _bbs_rows(self, full_results: Dict) -> List[Dict]:
        """Build a transparent preliminary BBS from actual selected bars.

        Cut lengths are explicit preliminary detailing assumptions, not final
        bar-bending drawings. They are therefore labelled as estimates.
        """
        rows = []

        def add(mark, element, location, spec, dia, qty, length_m):
            unit = RebarSelector.UNIT_WEIGHT_KG_M.get(dia, 0)
            total_len = qty * length_m
            rows.append({
                "Bar Mark": mark, "Element": element, "Location": location,
                "Specification": spec, "Diameter (mm)": dia,
                "Quantity": qty, "Cut Length (m)": round(length_m, 3),
                "Total Length (m)": round(total_len, 3),
                "Unit Weight (kg/m)": round(unit, 3),
                "Total Weight (kg)": round(total_len * unit, 2),
            })

        slab = full_results["slab"]
        sx, sy = slab["rebar_sx"], slab["rebar_sy"]
        cover_m = 0.025
        # Bottom X bars run in X; count is across Y.
        nx = math.ceil(self.ly * 1000 / sx["spacing"]) + 1
        ny = math.ceil(self.lx * 1000 / sy["spacing"]) + 1
        add("S01", "Slab", "Bottom X", sx["description"], sx["bar_diameter"],
            nx, max(0.0, self.lx - 2 * cover_m))
        add("S02", "Slab", "Bottom Y", sy["description"], sy["bar_diameter"],
            ny, max(0.0, self.ly - 2 * cover_m))

        beam = full_results["beam"]
        sb = beam["span_bars"]
        if sb.get("bars", 0):
            add("B01", "Beam", "Bottom span", sb["description"], sb["bar_diameter"],
                sb["bars"], self.ly)
        tb = beam["supp_bars"]
        if tb.get("bars", 0) and full_results["beam"]["M_support_kNm"] > 0:
            # Preliminary 0.30L anchorage extension each side of support.
            add("B02", "Beam", "Top support", tb["description"], tb["bar_diameter"],
                tb["bars"], 0.60 * self.ly)

        col = full_results["column"]["main_rebar"]
        if col.get("bars", 0):
            add("C01", "Column", "Longitudinal", col["description"], col["bar_diameter"],
                col["bars"] * self.num_storeys, 3.0)

        foot = full_results["footing"]
        fr = foot["rebar"]
        if fr.get("bar_diameter", 0):
            qx = math.ceil(foot["B_m"] * 1000 / fr["spacing"]) + 1
            qy = math.ceil(foot["L_m"] * 1000 / fr["spacing"]) + 1
            add("F01", "Footing", "Bottom X", fr["description"], fr["bar_diameter"],
                qx, max(0, foot["L_m"] - 2 * 0.05))
            add("F02", "Footing", "Bottom Y", fr["description"], fr["bar_diameter"],
                qy, max(0, foot["B_m"] - 2 * 0.05))
        return rows

    def generate_bbs_excel(self, full_results: Dict) -> bytes:
        output = io.BytesIO()
        rows = self._bbs_rows(full_results)
        df = pd.DataFrame(rows)
        summary = pd.DataFrame([{
            "Total steel weight (kg)": df["Total Weight (kg)"].sum() if not df.empty else 0,
            "Total steel weight (tonnes)": (df["Total Weight (kg)"].sum() / 1000) if not df.empty else 0,
            "NOTE": "Preliminary quantity estimate; final BBS requires engineer-reviewed detailing and anchorage/lap rules."
        }])
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="BBS_Schedule", index=False)
            summary.to_excel(writer, sheet_name="Summary", index=False)
        return output.getvalue()

    def bbs_rows(self, full_results: Dict) -> List[Dict]:
        return self._bbs_rows(full_results)
