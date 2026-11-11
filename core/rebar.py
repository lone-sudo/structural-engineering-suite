from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple


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
        max_bars: int = 6, min_bars: int = 2, *,
        b_w: float | None = None, cover: float = 25.0,
        link_dia: float = 8.0, max_layers: int = 1,
    ) -> List[Dict]:
        """Choose bar arrangements that actually fit in the beam width.

        The previous version only checked the bar count. For a 200 mm wide
        beam it would happily return 6Y25, an arrangement that cannot be
        placed in one layer (and would change the effective depth if placed
        in two). Where ``b_w`` is supplied, arrangements are filtered using
        the BS 8110 / EC2 clear-spacing rule ``max(25 mm, bar diameter)``.
        """
        if As_req < 0:
            raise ValueError("As_req cannot be negative.")

        if b_w is not None and b_w - 2.0 * (cover + link_dia) <= 0:
            return []

        options = []
        for dia in preferred_diameters:
            area = cls.BAR_AREAS[dia]
            n = max(min_bars, math.ceil(As_req / area))
            per_layer = None
            layers = 1
            if b_w is not None:
                available = b_w - 2.0 * (cover + link_dia)
                clear = max(25.0, float(dia))
                per_layer = int((available + clear) // (dia + clear))
                if per_layer < min_bars:
                    continue
                if n > per_layer * max_layers:
                    continue
                layers = math.ceil(n / per_layer)
            if n <= max_bars:
                option = {
                    "description": f"{n}Y{dia}",
                    "bars": n,
                    "bar_count": n,
                    "bar_diameter": dia,
                    "dia": dia,
                    "As_prov": round(n * area, 1),
                    "efficiency": round(100 * As_req / max(n * area, 1e-9), 1),
                }
                if per_layer is not None:
                    option["max_bars_per_layer"] = per_layer
                    option["layers"] = layers
                options.append(option)
        return sorted(options, key=lambda x: (x["As_prov"], x["bar_diameter"]))

    @classmethod
    def select_slab_spacing(
        cls, As_req_per_m: float, bar_dia: int = 12,
        max_spacing: int = 250, min_spacing: int = 75,
        code_max_spacing: int | None = None,
        allow_larger_bars: bool = True, max_bar_dia: int = 20,
    ) -> Dict:
        """Select a slab/footing bar spacing that never under-provides steel.

        The previous implementation rounded the required spacing *down* to a
        25 mm module and then forced it back up to a 75 mm minimum, which
        could return e.g. "Y10 @ 75" with less area than required while
        reporting a PASS in some callers. This version:
          * searches every 25 mm spacing up to the code maximum,
          * may step up the bar diameter if the requested one cannot
            satisfy the area at the minimum practical spacing,
          * returns ``passes_area=False`` and an explicit note when even the
            largest available arrangement cannot satisfy the demand.
        """
        if As_req_per_m < 0:
            raise ValueError("As_req_per_m cannot be negative.")
        if max_spacing < min_spacing:
            raise ValueError("max_spacing must be >= min_spacing.")

        bar_dia = int(bar_dia)
        allowed_max = min(int(max_spacing), int(code_max_spacing or max_spacing))
        allowed_max = max(allowed_max, int(min_spacing))

        diameters = [bar_dia]
        if allow_larger_bars:
            for dia in (12, 16, 20):
                if bar_dia < dia <= max_bar_dia and dia not in diameters:
                    diameters.append(dia)

        def _spacing_candidates() -> List[int]:
            values = set()
            top = (allowed_max // 25) * 25
            for s in range(int(top), int(min_spacing) - 1, -25):
                if s >= min_spacing:
                    values.add(int(s))
            values.add(int(allowed_max))
            values.add(int(min_spacing))
            return sorted(values, reverse=True)

        candidates: List[Dict] = []
        for dia in diameters:
            area = cls.BAR_AREAS.get(dia)
            if area is None:
                continue
            if As_req_per_m == 0:
                spacing = allowed_max
                As_prov = 1000.0 * area / spacing
                candidates.append({
                    "description": f"Y{dia} @ {spacing}mm c/c",
                    "spacing": spacing,
                    "bar_diameter": dia,
                    "As_prov": round(As_prov, 1),
                    "As_req": 0.0,
                    "passes_area": True,
                })
                continue
            for spacing in _spacing_candidates():
                As_prov = 1000.0 * area / spacing
                candidates.append({
                    "description": f"Y{dia} @ {spacing}mm c/c",
                    "spacing": spacing,
                    "bar_diameter": dia,
                    "As_prov": round(As_prov, 1),
                    "As_req": round(As_req_per_m, 1),
                    "passes_area": As_prov + 1e-9 >= As_req_per_m,
                })

        if not candidates:
            raise ValueError(f"Unsupported bar diameter: {bar_dia} mm.")

        passing = [c for c in candidates if c["passes_area"]]
        if passing:
            # Prefer a practical spacing (>=100 mm) before minimising area;
            # otherwise a congested 75 mm arrangement could beat a tidier
            # larger-bar layout that is easier to place and vibrate.
            return min(
                passing,
                key=lambda c: (c["spacing"] < 100, c["As_prov"], c["bar_diameter"]),
            )

        # Nothing passes. Return the strongest arrangement and say so
        # explicitly rather than silently rounding in the unsafe direction.
        best = max(candidates, key=lambda c: (c["As_prov"], -c["bar_diameter"]))
        best["passes_area"] = False
        best["note"] = (
            "Demand exceeds the capacity of the largest practical bar/spacing "
            "combination on this 1 m strip. Increase the section depth or "
            "provide a designed shear/flexural solution."
        )
        return best

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

    @classmethod
    def column_bar_positions(
        cls, n: int, b: float, h: float, cover: float,
        link_dia: float = 8.0, dia: float = 16.0,
    ) -> List[Tuple[float, float]]:
        """Return a symmetric perimeter bar layout for 4-12 column bars.

        This is shared by the on-screen section and the DXF export so they
        can never disagree. Previously both drawing paths silently drew only
        four corner bars for 10- and 12-bar columns.
        """
        if n not in (4, 6, 8, 10, 12):
            raise ValueError("Column layouts are defined for 4, 6, 8, 10 or 12 bars.")
        x0 = cover + link_dia + dia / 2.0
        x1 = b - x0
        y0 = cover + link_dia + dia / 2.0
        y1 = h - y0
        if x1 <= x0 or y1 <= y0:
            raise ValueError("Column section is too small for the specified cover and bars.")

        def line(xa: float, xb: float, count: int, y: float) -> List[Tuple[float, float]]:
            if count == 1:
                return [((xa + xb) / 2.0, y)]
            step = (xb - xa) / (count - 1)
            return [(xa + i * step, y) for i in range(count)]

        def side(ya: float, yb: float, count: int, x: float) -> List[Tuple[float, float]]:
            if count == 1:
                return [(x, (ya + yb) / 2.0)]
            step = (yb - ya) / (count - 1)
            return [(x, ya + i * step) for i in range(count)]

        if n == 4:
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        elif n == 6:
            pts = line(x0, x1, 3, y0) + line(x0, x1, 3, y1)
        elif n == 8:
            pts = line(x0, x1, 3, y0) + line(x0, x1, 3, y1) + side(y0, y1, 1, x0) + side(y0, y1, 1, x1)
        elif n == 10:
            pts = line(x0, x1, 4, y0) + line(x0, x1, 4, y1) + side(y0, y1, 1, x0) + side(y0, y1, 1, x1)
        else:  # 12
            pts = line(x0, x1, 4, y0) + line(x0, x1, 4, y1) + side(y0, y1, 2, x0) + side(y0, y1, 2, x1)

        # Remove exact duplicates (e.g. a side bar that coincides with a
        # corner bar) while preserving order.
        unique: List[Tuple[float, float]] = []
        for p in pts:
            if not any(abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6 for q in unique):
                unique.append(p)
        if len(unique) != n:
            # Fall back to an even perimeter ring rather than silently
            # drawing the wrong number of bars.
            perimeter = 2 * ((x1 - x0) + (y1 - y0))
            unique = []
            for i in range(n):
                s = perimeter * i / n
                if s < (x1 - x0):
                    unique.append((x0 + s, y0))
                elif s < (x1 - x0) + (y1 - y0):
                    unique.append((x1, y0 + (s - (x1 - x0))))
                elif s < 2 * (x1 - x0) + (y1 - y0):
                    unique.append((x1 - (s - (x1 - x0) - (y1 - y0)), y1))
                else:
                    unique.append((x0, y1 - (s - 2 * (x1 - x0) - (y1 - y0))))
        return unique
