from __future__ import annotations

import io
import re
from typing import Dict, List, Optional

import ezdxf


class CADReader:
    """Extracts structural grid lines and spans from DXF files.

    The previous implementation treated *every* LINE between 2 m and 15 m as
    a possible span, then returned a sorted set of line lengths. That meant
    walls, title-block lines and dimension strings could all be presented as
    "detected spans" with false confidence. This version only looks for
    axis-aligned lines and derives the grid from repeated X/Y coordinates,
    which is how a structural grid is actually drawn. If no clear grid is
    found it returns ``None`` rather than a list of arbitrary lengths.
    """

    # DXF $INSUNITS codes we can map with confidence; 0 = unspecified.
    _INSUNITS_TO_METRES = {
        1: 0.0254,      # inches
        2: 0.3048,      # feet
        4: 0.001,       # millimetres
        5: 0.01,        # centimetres
        6: 1.0,         # metres
    }

    @staticmethod
    def _cluster(values: List[float], tol: float = 0.05) -> List[float]:
        if not values:
            return []
        values = sorted(values)
        groups: List[List[float]] = [[values[0]]]
        for v in values[1:]:
            if abs(v - groups[-1][-1]) <= tol:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [round(sum(g) / len(g), 4) for g in groups]

    @staticmethod
    def parse_dxf_stream(file_bytes: bytes) -> Dict:
        dxf_str = file_bytes.decode("utf-8", errors="ignore")
        doc = ezdxf.read(io.StringIO(dxf_str))
        msp = doc.modelspace()

        insunits = None
        try:
            insunits = doc.header.get("$INSUNITS")
        except Exception:
            insunits = None

        unit_to_m: Optional[float] = CADReader._INSUNITS_TO_METRES.get(insunits) if insunits else None
        unit_source = (
            f"DXF header $INSUNITS={insunits}" if unit_to_m is not None
            else "not declared in DXF header — units guessed from line lengths and MUST be verified"
        )

        raw_lines = []
        inserts = []
        for entity in msp:
            if entity.dxftype() == "LINE":
                start, end = entity.dxf.start, entity.dxf.end
                dx = abs(end.x - start.x)
                dy = abs(end.y - start.y)
                raw_lines.append((dx, dy, start.x, start.y, end.x, end.y))
            elif entity.dxftype() in ("INSERT", "POINT"):
                inserts.append(entity)

        # Guess the drawing unit only when the header is silent.
        if unit_to_m is None:
            max_len = max((max(dx, dy) for dx, dy, *_ in raw_lines), default=0.0)
            scale = 0.001 if max_len > 50.0 else 1.0
        else:
            scale = unit_to_m

        x_coords: List[float] = []
        y_coords: List[float] = []
        for dx, dy, x1, y1, x2, y2 in raw_lines:
            if dx <= 1e-9 and dy > 1.0:
                x_coords.append(x1 * scale)
            elif dy <= 1e-9 and dx > 1.0:
                y_coords.append(y1 * scale)

        xs = CADReader._cluster(x_coords)
        ys = CADReader._cluster(y_coords)

        def spacings(coords: List[float]) -> List[float]:
            diffs = [round(b - a, 3) for a, b in zip(coords, coords[1:])]
            return sorted({d for d in diffs if 1.5 <= d <= 15.0})

        x_spans = spacings(xs)
        y_spans = spacings(ys)

        detected = bool(x_spans or y_spans)
        detected_spans = None
        if x_spans and y_spans:
            detected_spans = [x_spans[0], y_spans[0]]
        elif x_spans:
            detected_spans = [x_spans[0], x_spans[0]]
        elif y_spans:
            detected_spans = [y_spans[0], y_spans[0]]

        column_blocks = [
            e for e in inserts
            if e.dxftype() == "INSERT" and "COL" in str(getattr(e.dxf, "name", "")).upper()
        ]

        return {
            "total_entities": len(list(msp)),
            "detected_spans": detected_spans,
            "x_spans": x_spans[:8],
            "y_spans": y_spans[:8],
            "spans_detected": detected,
            "unit_confidence": "declared" if unit_to_m is not None else "guessed",
            "unit_source": unit_source,
            "grid_x_lines": len(xs),
            "grid_y_lines": len(ys),
            "total_columns_found": len(column_blocks) or len(inserts),
            "detection_note": (
                "Spans are derived from repeated X/Y coordinates of axis-aligned lines, "
                "not from arbitrary line lengths. Confirm against the drawing title block."
            ),
        }
