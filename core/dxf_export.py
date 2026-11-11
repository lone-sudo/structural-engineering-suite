"""Generates real, dimensioned DXF reinforcement detail drawings — the kind a
draughtsman or contractor can actually open in AutoCAD/BricsCAD/LibreCAD —
as opposed to the schematic on-screen Plotly previews in core/visualizer.py.

Every drawing carries an explicit "PRELIMINARY — NOT FOR CONSTRUCTION" note
in its title block. This module produces a geometrically correct detail of
what the calculation engine selected; it does not perform any new design
checks and does not claim construction-issue accuracy for cover, laps, bends
or bar schedules beyond what the calling element module already computed.
"""
from __future__ import annotations

import io
from datetime import date
from typing import Dict, List, Optional, Tuple

import ezdxf
from ezdxf.enums import TextEntityAlignment

from core.rebar import RebarSelector

_LAYERS = {
    "OUTLINE": {"color": 5},       # blue
    "REBAR-MAIN": {"color": 1},    # red
    "REBAR-LINKS": {"color": 3},   # green
    "DIMENSIONS": {"color": 8},    # grey
    "TEXT": {"color": 7},          # white/black
    "TITLEBLOCK": {"color": 7},
    "CENTERLINE": {"color": 6},    # magenta, dashed
}


def _new_doc():
    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for name, props in _LAYERS.items():
        doc.layers.add(name=name, color=props["color"])
    return doc, msp


def _dim_line(msp, x0: float, y0: float, x1: float, y1: float, text: str,
              offset: float = 0.0, vertical: bool = False):
    """A simple, dependency-free linear dimension: extension ticks + a
    dimension line + centred text. Avoids ezdxf's DIMSTYLE machinery so the
    output stays predictable across CAD viewers."""
    layer = "DIMENSIONS"
    tick = 4.0
    if vertical:
        dx = offset
        msp.add_line((x0, y0), (x0 + dx, y0), dxfattribs={"layer": layer})
        msp.add_line((x1, y1), (x1 + dx, y1), dxfattribs={"layer": layer})
        msp.add_line((x0 + dx, y0), (x1 + dx, y1), dxfattribs={"layer": layer})
        for yy in (y0, y1):
            msp.add_line((x0 + dx - tick, yy), (x0 + dx + tick, yy), dxfattribs={"layer": layer})
        mid_y = (y0 + y1) / 2.0
        t = msp.add_text(text, dxfattribs={"layer": layer, "height": 6, "rotation": 90})
        t.set_placement((x0 + dx + 8, mid_y), align=TextEntityAlignment.MIDDLE_LEFT)
    else:
        dy = offset
        msp.add_line((x0, y0), (x0, y0 + dy), dxfattribs={"layer": layer})
        msp.add_line((x1, y1), (x1, y1 + dy), dxfattribs={"layer": layer})
        msp.add_line((x0, y0 + dy), (x1, y1 + dy), dxfattribs={"layer": layer})
        for xx in (x0, x1):
            msp.add_line((xx, y0 + dy - tick), (xx, y0 + dy + tick), dxfattribs={"layer": layer})
        mid_x = (x0 + x1) / 2.0
        t = msp.add_text(text, dxfattribs={"layer": layer, "height": 6})
        t.set_placement((mid_x, y0 + dy + 8), align=TextEntityAlignment.BOTTOM_CENTER)


def _leader_note(msp, from_xy: Tuple[float, float], to_xy: Tuple[float, float], text: str):
    msp.add_line(from_xy, to_xy, dxfattribs={"layer": "TEXT"})
    t = msp.add_text(text, dxfattribs={"layer": "TEXT", "height": 5.5})
    t.set_placement(to_xy, align=TextEntityAlignment.MIDDLE_LEFT)


def _title_block(msp, x: float, y: float, width: float, rows: List[Tuple[str, str]],
                  element_title: str, code: str, project_name: str, engineer_name: str):
    h = 14 * (len(rows) + 4)
    msp.add_lwpolyline(
        [(x, y), (x + width, y), (x + width, y + h), (x, y + h), (x, y)],
        dxfattribs={"layer": "TITLEBLOCK"}
    )
    msp.add_line((x, y + h - 34), (x + width, y + h - 34), dxfattribs={"layer": "TITLEBLOCK"})
    t = msp.add_text(f"STRUCTURAL RCC SUITE — {element_title.upper()}",
                      dxfattribs={"layer": "TITLEBLOCK", "height": 7})
    t.set_placement((x + 6, y + h - 12), align=TextEntityAlignment.MIDDLE_LEFT)
    sub = msp.add_text(f"Code: {code}   Project: {project_name or '-'}   Engineer: {engineer_name or '-'}   Date: {date.today().isoformat()}",
                        dxfattribs={"layer": "TITLEBLOCK", "height": 4.2})
    sub.set_placement((x + 6, y + h - 26), align=TextEntityAlignment.MIDDLE_LEFT)

    yy = y + h - 44
    for label, value in rows:
        row = msp.add_text(f"{label}: {value}", dxfattribs={"layer": "TITLEBLOCK", "height": 4.5})
        row.set_placement((x + 6, yy), align=TextEntityAlignment.MIDDLE_LEFT)
        yy -= 12

    warn = msp.add_text(
        "PRELIMINARY DESIGN AID — NOT FOR CONSTRUCTION. Independent engineering review, "
        "detailing check (laps, hooks, curtailment, cover) and construction drawings required before use on site.",
        dxfattribs={"layer": "TITLEBLOCK", "height": 3.6}
    )
    warn.set_placement((x + 6, y + 6), align=TextEntityAlignment.MIDDLE_LEFT)


def _bar_row(msp, xs: List[float], y: float, dia: int, layer: str = "REBAR-MAIN", label: Optional[str] = None):
    for x in xs:
        msp.add_circle((x, y), dia / 2.0, dxfattribs={"layer": layer})
    if label and xs:
        t = msp.add_text(label, dxfattribs={"layer": "TEXT", "height": 5})
        t.set_placement((xs[-1] + dia, y), align=TextEntityAlignment.MIDDLE_LEFT)


def _linspace(a: float, b: float, n: int) -> List[float]:
    if n <= 1:
        return [(a + b) / 2.0]
    step = (b - a) / (n - 1)
    return [a + i * step for i in range(n)]


# ---------------------------------------------------------------------------
# BEAM
# ---------------------------------------------------------------------------

def generate_beam_dxf(
    b_res: Dict, b_w: float, h_overall: float, cover: float, code: str,
    project_name: str = "", engineer_name: str = ""
) -> bytes:
    doc, msp = _new_doc()

    span_bars = b_res["span_bars"]
    supp_bars = b_res["supp_bars"]
    link_dia = 8
    try:
        link_dia = int(b_res["link_schedule"].split(" ")[0].lstrip("YH"))
    except Exception:
        pass

    def _draw_section(ox: float, oy: float, top_bars: Dict, bot_bars: Dict, title: str):
        msp.add_lwpolyline(
            [(ox, oy), (ox + b_w, oy), (ox + b_w, oy + h_overall), (ox, oy + h_overall), (ox, oy)],
            dxfattribs={"layer": "OUTLINE"}
        )
        lx0, ly0 = ox + cover, oy + cover
        lx1, ly1 = ox + b_w - cover, oy + h_overall - cover
        msp.add_lwpolyline([(lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1), (lx0, ly0)],
                            dxfattribs={"layer": "REBAR-LINKS"})

        bot_dia = bot_bars.get("bar_diameter", 16)
        bot_n = bot_bars.get("bar_count", 2)
        bot_y = oy + cover + link_dia + bot_dia / 2.0
        bot_xs = _linspace(ox + cover + link_dia + bot_dia / 2.0, ox + b_w - cover - link_dia - bot_dia / 2.0, bot_n)
        _bar_row(msp, bot_xs, bot_y, bot_dia, label=f"{bot_n}Y{bot_dia} (bottom)")

        top_dia = top_bars.get("bar_diameter", 12)
        top_n = top_bars.get("bar_count", 2)
        top_y = oy + h_overall - cover - link_dia - top_dia / 2.0
        top_xs = _linspace(ox + cover + link_dia + top_dia / 2.0, ox + b_w - cover - link_dia - top_dia / 2.0, top_n)
        _bar_row(msp, top_xs, top_y, top_dia, label=f"{top_n}Y{top_dia} (top)")

        _dim_line(msp, ox, oy, ox + b_w, oy, f"{int(b_w)}mm", offset=-20)
        _dim_line(msp, ox, oy, ox, oy + h_overall, f"{int(h_overall)}mm", offset=-20, vertical=True)

        tt = msp.add_text(title, dxfattribs={"layer": "TEXT", "height": 7})
        tt.set_placement((ox + b_w / 2.0, oy + h_overall + 35), align=TextEntityAlignment.MIDDLE_CENTER)

    _draw_section(0, 0, top_bars=supp_bars, bot_bars=span_bars, title="MID-SPAN SECTION (bottom steel governs)")
    gap = b_w + 150
    _draw_section(gap, 0, top_bars=supp_bars, bot_bars=span_bars, title="SUPPORT SECTION (top steel governs)")
    # At the support section, swap emphasis: top bars are the main tension steel there.
    # (Kept as the same computed bar sets — this is a schematic pairing of the two
    # already-designed reinforcement sets, not a new design.)

    _leader_note(msp, (gap + b_w + 10, h_overall * 0.6), (gap + b_w + 60, h_overall * 0.6), b_res["link_schedule"])

    rows = [
        ("Span moment", f"{b_res['M_span_kNm']} kNm"),
        ("Support moment", f"{b_res['M_support_kNm']} kNm"),
        ("Bottom steel (span)", span_bars["description"]),
        ("Top steel (support)", supp_bars["description"]),
        ("Links", b_res["link_schedule"]),
        ("Shear status", b_res["shear_status"]),
        ("Deflection screening", b_res.get("deflection_status", "n/a")),
    ]
    _title_block(msp, 0, -230, gap + b_w, rows, "Beam Reinforcement Detail", code, project_name, engineer_name)

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# COLUMN
# ---------------------------------------------------------------------------

def generate_column_dxf(
    col_res: Dict, b: float, h: float, cover: float, code: str,
    project_name: str = "", engineer_name: str = ""
) -> bytes:
    doc, msp = _new_doc()

    main = col_res["main_rebar"]
    dia = main.get("bar_diameter", 16)
    n = main.get("bar_count", 4)
    link_dia = 8
    try:
        link_dia = int(col_res["link_schedule"].split(" ")[0].lstrip("YH"))
    except Exception:
        pass

    msp.add_lwpolyline([(0, 0), (b, 0), (b, h), (0, h), (0, 0)], dxfattribs={"layer": "OUTLINE"})
    lx0, ly0, lx1, ly1 = cover, cover, b - cover, h - cover
    msp.add_lwpolyline([(lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1), (lx0, ly0)],
                        dxfattribs={"layer": "REBAR-LINKS"})

    cx0, cx1 = cover + link_dia + dia / 2.0, b - cover - link_dia - dia / 2.0
    cy0, cy1 = cover + link_dia + dia / 2.0, h - cover - link_dia - dia / 2.0
    try:
        coords = RebarSelector.column_bar_positions(n, b, h, cover, link_dia, dia)
    except (ValueError, TypeError):
        coords = [(cx0, cy0), (cx1, cy0), (cx0, cy1), (cx1, cy1)]
    for x, y in coords:
        msp.add_circle((x, y), dia / 2.0, dxfattribs={"layer": "REBAR-MAIN"})

    _dim_line(msp, 0, 0, b, 0, f"{int(b)}mm", offset=-20)
    _dim_line(msp, 0, 0, 0, h, f"{int(h)}mm", offset=-20, vertical=True)
    _leader_note(msp, (cx1, cy1), (b + 20, h * 0.75), f"{n}Y{dia} main bars")
    _leader_note(msp, (lx1, ly0), (b + 20, h * 0.25), col_res["link_schedule"])

    rows = [
        (f"Axial force ({col_res['axial_force_label']})", f"{col_res['N_ult_total_kN']} kN"),
        ("Axial resistance", f"{col_res['N_rd_kN']} kN — {col_res['axial_resistance_status']}"),
        ("Main bars", main["description"]),
        ("Links", col_res["link_schedule"]),
        ("Short column", "Yes" if col_res["is_short"] else "No — slender, see calc sheet"),
        ("Moment interaction", f"{col_res.get('moment_status', 'n/a')} (simplified check — see calc sheet)"),
    ]
    _title_block(msp, 0, -190, max(b, 260), rows, "Column Reinforcement Detail", code, project_name, engineer_name)

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# FOOTING
# ---------------------------------------------------------------------------

def generate_footing_dxf(
    f_res: Dict, pad_L_m: float, pad_B_m: float, col_cx: float, col_cy: float, code: str,
    project_name: str = "", engineer_name: str = ""
) -> bytes:
    doc, msp = _new_doc()
    L, B = pad_L_m * 1000.0, pad_B_m * 1000.0
    rebar = f_res["rebar"]
    dia = rebar.get("bar_diameter", 12)
    spacing = rebar.get("spacing", 200)
    cover = 50.0

    msp.add_lwpolyline([(0, 0), (L, 0), (L, B), (0, B), (0, 0)], dxfattribs={"layer": "OUTLINE"})
    ccx0, ccy0 = (L - col_cx) / 2.0, (B - col_cy) / 2.0
    msp.add_lwpolyline(
        [(ccx0, ccy0), (ccx0 + col_cx, ccy0), (ccx0 + col_cx, ccy0 + col_cy), (ccx0, ccy0 + col_cy), (ccx0, ccy0)],
        dxfattribs={"layer": "CENTERLINE", "linetype": "DASHED"}
    )

    n_x = max(2, int((L - 2 * cover) // spacing) + 1)
    n_y = max(2, int((B - 2 * cover) // spacing) + 1)
    for x in _linspace(cover, L - cover, n_x):
        msp.add_line((x, cover), (x, B - cover), dxfattribs={"layer": "REBAR-MAIN"})
    for y in _linspace(cover, B - cover, n_y):
        msp.add_line((cover, y), (L - cover, y), dxfattribs={"layer": "REBAR-MAIN"})

    _dim_line(msp, 0, 0, L, 0, f"{L/1000:.2f}m", offset=-40)
    _dim_line(msp, 0, 0, 0, B, f"{B/1000:.2f}m", offset=-40, vertical=True)
    _leader_note(msp, (L * 0.5, B * 0.5), (L + 30, B * 0.6), f"{rebar['description']} (both ways)")

    rows = [
        ("Plan size", f"{pad_L_m:.2f}m × {pad_B_m:.2f}m"),
        ("Reinforcement mat", rebar["description"]),
        ("Service bearing pressure", f"{f_res.get('q_service_kpa', 'n/a')} kN/m²"),
        ("Punching shear", "see calc sheet audit"),
    ]
    _title_block(msp, 0, -240, max(L, 300), rows, "Pad Footing Reinforcement Plan", code, project_name, engineer_name)

    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")
