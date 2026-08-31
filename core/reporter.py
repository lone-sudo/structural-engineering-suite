from __future__ import annotations

from html import escape
from typing import Dict, List


class StructuralReporter:
    """Transparent reports: calculations, checks, limitations and quantities."""

    @staticmethod
    def audit_detailing(full_res: Dict) -> List[Dict[str, str]]:
        warnings = []
        for element in ("slab", "beam", "column", "footing"):
            audit = full_res.get(element, {}).get("audit", {})
            if audit.get("overall_status") == "FAIL":
                warnings.append({
                    "level": "error", "element": element.title(),
                    "message": "One or more design checks failed."
                })
            elif audit.get("overall_status") == "NOT CHECKED":
                warnings.append({
                    "level": "warning", "element": element.title(),
                    "message": "One or more required checks are not implemented; this is not a completed design."
                })
        return warnings

    @staticmethod
    def calculate_tonnage_and_cost(
        full_res: Dict, cost_per_tonne_kes: float = 145000.0,
        bbs_rows: List[Dict] | None = None, wastage_pct: float = 5.0
    ) -> Dict:
        """Estimate reinforcement procurement quantity and material cost.

        The base quantity comes only from BBS rows. Nominal bar mass is calculated
        from diameter using d²/162 kg/m in RebarSelector. A separate, user-editable
        procurement allowance is then applied; this is not treated as structural
        steel actually detailed in the member.
        """
        if cost_per_tonne_kes < 0:
            raise ValueError("Steel cost per tonne cannot be negative.")
        if wastage_pct < 0 or wastage_pct > 100:
            raise ValueError("Wastage/procurement allowance must be between 0 and 100%.")
        rows = bbs_rows or []
        breakdown = {}
        element_breakdown = {}
        total_kg = 0.0
        for row in rows:
            dia = int(row["Diameter (mm)"])
            element = str(row.get("Element", "Other"))
            kg = float(row["Total Weight (kg)"])
            if kg < 0:
                raise ValueError("BBS row weight cannot be negative.")
            breakdown[dia] = breakdown.get(dia, 0.0) + kg
            element_breakdown[element] = element_breakdown.get(element, 0.0) + kg
            total_kg += kg
        wastage_kg = total_kg * wastage_pct / 100.0
        procurement_kg = total_kg + wastage_kg
        tonnes = total_kg / 1000.0
        procurement_tonnes = procurement_kg / 1000.0
        return {
            "breakdown_kg": {d: round(v, 2) for d, v in sorted(breakdown.items())},
            "element_breakdown_kg": {e: round(v, 2) for e, v in sorted(element_breakdown.items())},
            "total_kg": round(total_kg, 2),
            "total_tonnes": round(tonnes, 3),
            "wastage_pct": round(wastage_pct, 2),
            "wastage_kg": round(wastage_kg, 2),
            "procurement_kg": round(procurement_kg, 2),
            "procurement_tonnes": round(procurement_tonnes, 3),
            "estimated_cost_kes": round(procurement_tonnes * cost_per_tonne_kes, 2),
            "quantity_basis": "Preliminary BBS quantity using nominal d²/162 bar mass and explicit cut-length assumptions; procurement quantity adds the selected allowance. This is not a final BBS or cutting/wastage optimization.",
        }

    @staticmethod
    def generate_single_element_report(
        element_title: str, data: Dict, code: str, f_cu: float, f_y: float,
        project_name: str = "", engineer_name: str = ""
    ) -> str:
        """Standalone calc-sheet export for one design module (beam, column,
        footing or slab), so an engineer isn't forced through the whole-building
        workflow just to get a printable, attachable record of one calc."""

        def status_badge(status: str) -> str:
            cls = {"PASS": "pass", "FAIL": "fail", "NOT CHECKED": "nc", "WARNING": "warn"}.get(status, "nc")
            return f'<span class="badge {cls}">{escape(status)}</span>'

        audit = data.get("audit", {})
        rows = []
        for check in audit.get("checks", []):
            rows.append(
                f"<tr><td>{escape(check['name'])}</td>"
                f"<td>{'' if check.get('demand') is None else check['demand']}</td>"
                f"<td>{'' if check.get('capacity') is None else check['capacity']}</td>"
                f"<td>{escape(check.get('unit',''))}</td>"
                f"<td>{status_badge(check['status'])}</td>"
                f"<td>{escape(check.get('message',''))}</td></tr>"
            )
        overall = escape(audit.get("overall_status", "NOT CHECKED"))
        limitations = "".join(f"<li>{escape(x)}</li>" for x in data.get("limitations", []))

        meta_rows = "".join(
            f"<tr><td>{escape(str(k))}</td><td>{escape(str(v))}</td></tr>"
            for k, v in data.items()
            if k not in {"audit", "limitations", "rebar", "rebar_sx", "rebar_sy", "rebar_sx_neg", "rebar_sy_neg", "span_bars", "supp_bars", "span_flex", "supp_flex", "main_rebar", "dist_rebar"}
            and not isinstance(v, dict)
        )

        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(element_title)} Calculation Sheet</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;color:#25313b;line-height:1.45}}
h1{{margin-bottom:4px}} h2{{border-bottom:2px solid #555;padding-bottom:5px}}
table{{border-collapse:collapse;width:100%;margin:12px 0 22px}}
th,td{{border:1px solid #bbb;padding:7px;text-align:left;font-size:13px}}
th{{background:#eee}} .badge{{padding:3px 7px;border-radius:4px;font-weight:bold}}
.pass{{background:#d9f2df}} .fail{{background:#ffd9d9}} .nc{{background:#ffeab5}} .warn{{background:#ffeab5}}
.notice{{border:1px solid #c88;background:#fff5df;padding:14px;margin:15px 0}}
</style></head><body>
<h1>Structural RCC Suite — {escape(element_title)} Calculation Sheet</h1>
<p>{f"<strong>Project:</strong> {escape(project_name)} | " if project_name else ""}
{f"<strong>Engineer:</strong> {escape(engineer_name)} | " if engineer_name else ""}
<strong>Code:</strong> {escape(code)} | <strong>Concrete input:</strong> fcu = {f_cu:g} MPa |
<strong>Steel:</strong> fy = {f_y:g} MPa</p>
<div class="notice"><strong>Engineering status:</strong> {status_badge(overall)}.
This report is a computer-generated preliminary calculation aid. It is not a
construction certificate, statutory submission, or substitute for independent
review by a suitably qualified structural engineer.</div>
<h2>Calculation parameters and results</h2>
<table><tr><th>Item</th><th>Value</th></tr>{meta_rows}</table>
<h2>Design verification</h2>
<table><tr><th>Check</th><th>Demand</th><th>Capacity</th><th>Unit</th><th>Status</th><th>Notes</th></tr>
{"".join(rows)}</table>
<h2>Limitations</h2><ul>{limitations}</ul>
</body></html>"""

    @staticmethod
    def generate_html_report(full_res: Dict, code: str, f_cu: float, f_y: float) -> str:
        pad_L, pad_B, q_service = full_res["pad_size"]

        def status_badge(status: str) -> str:
            cls = {
                "PASS": "pass", "FAIL": "fail", "NOT CHECKED": "nc",
                "WARNING": "warn"
            }.get(status, "nc")
            return f'<span class="badge {cls}">{escape(status)}</span>'

        sections = []
        for key, title in (
            ("slab", "Two-way slab"),
            ("beam", "Continuous beam"),
            ("column", "Column"),
            ("footing", "Pad footing"),
        ):
            data = full_res[key]
            audit = data.get("audit", {})
            rows = []
            for check in audit.get("checks", []):
                rows.append(
                    f"<tr><td>{escape(check['name'])}</td>"
                    f"<td>{'' if check.get('demand') is None else check['demand']}</td>"
                    f"<td>{'' if check.get('capacity') is None else check['capacity']}</td>"
                    f"<td>{escape(check.get('unit',''))}</td>"
                    f"<td>{status_badge(check['status'])}</td>"
                    f"<td>{escape(check.get('message',''))}</td></tr>"
                )
            sections.append(
                f"<h3>{escape(title)}</h3>"
                f"<p><strong>Overall:</strong> {status_badge(audit.get('overall_status','NOT CHECKED'))}</p>"
                f"<table><tr><th>Check</th><th>Demand</th><th>Capacity</th><th>Unit</th><th>Status</th><th>Notes</th></tr>"
                + "".join(rows) + "</table>"
                + "<h4>Limitations</h4><ul>"
                + "".join(f"<li>{escape(x)}</li>" for x in data.get("limitations", []))
                + "</ul>"
            )

        overall = escape(full_res.get("summary", {}).get("overall_status", "NOT CHECKED"))
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Structural Calculation Report</title>
<style>
body{{font-family:Arial,sans-serif;margin:32px;color:#25313b;line-height:1.45}}
h1{{margin-bottom:4px}} h2{{border-bottom:2px solid #555;padding-bottom:5px}}
table{{border-collapse:collapse;width:100%;margin:12px 0 22px}}
th,td{{border:1px solid #bbb;padding:7px;text-align:left;font-size:13px}}
th{{background:#eee}} .badge{{padding:3px 7px;border-radius:4px;font-weight:bold}}
.pass{{background:#d9f2df}} .fail{{background:#ffd9d9}} .nc{{background:#ffeab5}} .warn{{background:#ffeab5}}
.notice{{border:1px solid #c88;background:#fff5df;padding:14px;margin:15px 0}}
</style></head><body>
<h1>Structural RCC Suite — Calculation Report</h1>
<p><strong>Code:</strong> {escape(code)} |
<strong>Concrete input:</strong> fcu = {f_cu:g} MPa |
<strong>Steel:</strong> fy = {f_y:g} MPa</p>
<div class="notice"><strong>Engineering status:</strong> {status_badge(overall)}.
This report is a computer-generated preliminary calculation aid. It is not a
construction certificate, statutory submission, or substitute for independent
review by a suitably qualified structural engineer.</div>
<p><strong>Representative footing size:</strong> {pad_L:.2f} m × {pad_B:.2f} m;
service bearing pressure = {q_service:.2f} kN/m².</p>
{''.join(sections)}
<h2>Important assumptions</h2>
<ul>
<li>Loads are carried as separate Gk and Qk quantities until ULS combination.</li>
<li>The automated building workflow represents one internal gravity bay; it does not analyse a complete building frame.</li>
<li>Any item marked NOT CHECKED must be independently designed before construction use.</li>
<li>BS 8110 is a legacy standard; project-specific national requirements and the applicable current code must be confirmed.</li>
</ul>
</body></html>"""
