from __future__ import annotations

import io
import ezdxf
from typing import Dict, List, Optional


class CADReader:
    """Extracts structural grid lines, spans, and column coordinates from DXF files.

    Nothing here is silently invented. When a value cannot be confidently
    detected, the corresponding field is returned as None and the "confidence"
    or "unit_source" fields explain why, so the caller (app.py) can show the
    engineer exactly what was read versus what still needs manual entry.
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
            else "not declared in DXF header — lengths shown are a best-effort heuristic guess and MUST be verified"
        )

        lines_raw = []
        points = []
        entity_count = 0

        for entity in msp:
            entity_count += 1
            if entity.dxftype() == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                dx = abs(end.x - start.x)
                dy = abs(end.y - start.y)
                length = (dx**2 + dy**2) ** 0.5
                lines_raw.append(length)
            elif entity.dxftype() in ["POINT", "INSERT"]:
                try:
                    pt = (entity.dxf.insert.x, entity.dxf.insert.y)
                except AttributeError:
                    try:
                        pt = (entity.dxf.location.x, entity.dxf.location.y)
                    except AttributeError:
                        continue
                points.append(pt)

        if unit_to_m is not None:
            lengths_m = [l * unit_to_m for l in lines_raw]
            confidence = "declared"
        else:
            # Best-effort fallback only when the header doesn't say: assume
            # values over 50 drawing units are millimetres, otherwise metres.
            lengths_m = [(l / 1000.0 if l > 50 else l) for l in lines_raw]
            confidence = "guessed"

        filtered_spans = sorted({round(v, 2) for v in lengths_m if 2.0 <= v <= 15.0})

        detected = bool(filtered_spans)
        return {
            "total_entities": entity_count,
            "detected_spans": filtered_spans[:6] if detected else None,
            "spans_detected": detected,
            "unit_confidence": confidence,
            "unit_source": unit_source,
            "total_columns_found": len(points),
        }
