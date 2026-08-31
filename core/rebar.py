from __future__ import annotations

import math
from typing import Dict, List, Sequence


class RebarSelector:
    """Selects practical reinforcement arrangements and checks basic geometry."""

    BAR_AREAS = {
        8: 50.27, 10: 78.54, 12: 113.10, 16: 201.06,
        20: 314.16, 25: 490.87, 32: 804.25,
    }
    # Nominal theoretical mass per metre, m = d² / 162 (kg/m).
    UNIT_WEIGHT_KG_M = {
        d: (d ** 2) / 162.0 for d in BAR_AREAS
    }

    @classmethod
    def select_beam_bars(
        cls, As_req: float, preferred_diameters: Sequence[int] = (12, 16, 20, 25),
        max_bars: int = 6, min_bars: int = 2
    ) -> List[Dict]:
        if As_req < 0:
            raise ValueError("As_req cannot be negative.")
        options = []
        for dia in preferred_diameters:
            area = cls.BAR_AREAS[dia]
            n = max(min_bars, math.ceil(As_req / area))
            if n <= max_bars:
                options.append({
                    "description": f"{n}Y{dia}",
                    "bars": n,
                    "bar_count": n,
                    "bar_diameter": dia,
                    "dia": dia,
                    "As_prov": round(n * area, 1),
                    "efficiency": round(100 * As_req / max(n * area, 1e-9), 1),
                })
        return sorted(options, key=lambda x: (x["As_prov"], x["bar_diameter"]))

    @classmethod
    def select_slab_spacing(
        cls, As_req_per_m: float, bar_dia: int = 12,
        max_spacing: int = 250, min_spacing: int = 75,
        code_max_spacing: int | None = None
    ) -> Dict:
        if As_req_per_m < 0:
            raise ValueError("As_req_per_m cannot be negative.")
        if bar_dia not in cls.BAR_AREAS:
            raise ValueError(f"Unsupported bar diameter: {bar_dia} mm.")
        if max_spacing < min_spacing:
            raise ValueError("max_spacing must be >= min_spacing.")

        allowed_max = min(max_spacing, code_max_spacing or max_spacing)
        area = cls.BAR_AREAS[bar_dia]
        if As_req_per_m == 0:
            spacing = allowed_max
        else:
            spacing_raw = 1000 * area / As_req_per_m
            spacing = min(allowed_max, int(spacing_raw // 25) * 25)
            spacing = max(spacing, min_spacing)

        As_prov = 1000 * area / spacing
        return {
            "description": f"Y{bar_dia} @ {spacing}mm c/c",
            "spacing": spacing,
            "bar_diameter": bar_dia,
            "As_prov": round(As_prov, 1),
            "As_req": round(As_req_per_m, 1),
            "passes_area": As_prov + 1e-9 >= As_req_per_m,
        }

    @classmethod
    def select_column_bars(
        cls, As_req: float, b: float, h: float, cover: float,
        preferred_diameters: Sequence[int] = (12, 16, 20, 25, 32),
        max_bars: int = 12,
    ) -> Dict:
        """Choose a symmetric rectangular layout, not just a bar count."""
        if As_req <= 0:
            As_req = 0.0

        layouts = []
        # For 4/6/8/10/12 bars: corners + symmetric face bars.
        for n in (4, 6, 8, 10, 12):
            if n > max_bars:
                continue
            for dia in preferred_diameters:
                if dia not in cls.BAR_AREAS:
                    continue
                # Minimum clear distance between longitudinal bars.
                nx = max(2, n // 2)
                ny = n - nx + 2
                x_clear = b - 2 * (cover + dia / 2)
                y_clear = h - 2 * (cover + dia / 2)
                if x_clear <= 0 or y_clear <= 0:
                    continue
                # Conservative envelope check for evenly distributed perimeter bars.
                max_spacing = max(x_clear / max(nx - 1, 1), y_clear / max(ny - 1, 1))
                if max_spacing > 300:
                    continue
                As = n * cls.BAR_AREAS[dia]
                if As >= As_req:
                    layouts.append({
                        "description": f"{n}Y{dia}",
                        "bars": n,
                        "bar_count": n,
                        "bar_diameter": dia,
                        "dia": dia,
                        "As_prov": round(As, 1),
                        "layout": "symmetric perimeter arrangement",
                        "max_approx_bar_spacing_mm": round(max_spacing, 1),
                        "efficiency": round(100 * As_req / As, 1) if As else 0,
                    })
        if not layouts:
            return {
                "description": "NO VALID STANDARD ARRANGEMENT",
                "bars": 0,
                "bar_count": 0,
                "bar_diameter": 0,
                "dia": 0,
                "As_prov": 0.0,
                "layout": "Manual detailing required",
                "max_approx_bar_spacing_mm": None,
                "efficiency": 0.0,
            }
        return min(layouts, key=lambda x: (x["As_prov"], x["bar_diameter"]))
