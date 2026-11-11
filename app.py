import streamlit as st

# Heavy/optional modules are imported only when their workflow is opened.
# This keeps the app's initial startup lighter in RAM and CPU.
from core.auth import require_access_key
from core.geometry import GridGeometry, parse_spacings

st.set_page_config(page_title="Structural RCC Suite", layout="wide")

if "global_settings" not in st.session_state:
    st.session_state.global_settings = {
        "code": "BS8110",
        "f_cu": 25.0,
        "f_y": 460.0,
        "cover": 25.0,
        "exposure": "Mild",
    }

code_choice = st.session_state.global_settings["code"]
f_cu = st.session_state.global_settings["f_cu"]
f_y = st.session_state.global_settings["f_y"]
cover = st.session_state.global_settings.get("cover", 25.0)

# ==========================================
# 0. SINGLE-USE ACCESS KEY ENFORCEMENT
# ==========================================
require_access_key()

if st.session_state.license_user == "Open Source Mode":
    st.sidebar.caption("Open-source mode · no licence required")
elif st.session_state.license_user == "Local Development Mode":
    st.sidebar.caption("Local development mode")
else:
    st.sidebar.success(f"Active License: {st.session_state.license_user}")

# CSS to ensure metric values and prices wrap completely without truncation
st.markdown("""
<style>
    div[data-testid="stMetricValue"] {
        font-size: 1.40rem !important;
        white-space: normal !important;
        word-break: break-word !important;
    }
    div[data-testid="InputInstructions"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

STATUS_META = {
    "PASS": ("PASS", "Verified check passed."),
    "FAIL": ("FAIL", "Verified check failed."),
    "NOT CHECKED": ("NOT CHECKED", "This check is not implemented sufficiently to claim code compliance."),
    "WARNING": ("WARNING", "Check completed with a warning or applicability limitation."),
    "NOT APPLICABLE": ("N/A", "This check does not apply to the selected case."),
}

def show_audit(audit: dict, title: str = "Design verification"):
    """Compact, transparent verification table for engineers."""
    checks = audit.get("checks", []) if audit else []
    if not checks:
        return
    st.markdown(f"### {title}")
    for check in checks:
        status = check.get("status", "NOT CHECKED")
        icon, explanation = STATUS_META.get(status, ("", "Status requires review."))
        label = check.get("name", "Check")
        message = check.get("message") or explanation
        demand = check.get("demand")
        capacity = check.get("capacity")
        unit = check.get("unit", "")
        details = []
        if demand is not None:
            details.append(f"Demand: {demand:g} {unit}".strip())
        if capacity is not None:
            details.append(f"Capacity: {capacity:g} {unit}".strip())
        suffix = " · ".join(details)
        st.write(f"{icon} **{label}: {status}**" + (f" — {suffix}" if suffix else ""))
        if status in {"NOT CHECKED", "WARNING"}:
            st.caption(message)

    with st.expander("❓ Ask about this result"):
        st.caption("Type a question about any check above — this searches the tool's own documentation and the exact messages shown here. It never invents a new engineering opinion.")
        q = st.text_input("Your question", key=f"help_q_{title}", label_visibility="collapsed", placeholder="e.g. why is this NOT CHECKED?")
        if q:
            from core.help_assistant import search as help_search
            hits = help_search(q, design_results=st.session_state.get("design_results"))
            if hits:
                for score, entry in hits:
                    st.markdown(f"**{entry['question']}**")
                    st.write(entry["answer"])
                    st.divider()
            else:
                st.info("No close match found. Try the full Help & Troubleshooting module in the sidebar, or rephrase your question.")


def download_calc_sheet(element_title: str, data: dict, key: str):
    """Standalone printable calc-sheet download for a single design module.

    Uses the settings stamped on the result, not whatever happens to be in
    the sidebar now, so a calc sheet can never silently acquire a different
    code or material grade from the one that was actually used.
    """
    from core.reporter import StructuralReporter
    project_name = st.session_state.get("project_name", "")
    engineer_name = st.session_state.get("engineer_name", "")
    stamped = (data or {}).get("_design_settings", {})
    html = StructuralReporter.generate_single_element_report(
        element_title, data,
        code=stamped.get("code", code_choice),
        f_cu=stamped.get("f_cu", f_cu),
        f_y=stamped.get("f_y", f_y),
        project_name=project_name, engineer_name=engineer_name,
    )
    st.download_button(
        f"📄 Download {element_title} calc sheet (HTML)", data=html,
        file_name=f"{element_title.lower().replace(' ', '_')}_calc_sheet.html",
        mime="text/html", key=f"dl_{key}"
    )


def download_dxf(element_title: str, dxf_bytes: bytes, key: str):
    """Real, dimensioned DXF reinforcement detail — openable in AutoCAD/
    BricsCAD/LibreCAD, not just a schematic on-screen preview."""
    st.download_button(
        f"📐 Download {element_title} reinforcement detail (DXF)", data=dxf_bytes,
        file_name=f"{element_title.lower().replace(' ', '_')}_detail.dxf",
        mime="application/dxf", key=f"dxf_{key}"
    )
    st.caption("Schematic detail drawing generated from the calculated reinforcement — verify laps, hooks, curtailment and cover before issuing for construction.")


if "project_data" not in st.session_state:
    st.session_state.project_data = {
        "has_drawing": False,
        "file_name": "",
        "pdf_images": [],
        "span_x": 4.0,
        "span_y": 5.0,
        "slab_thick": 150.0,
        "pad_dim": 1350.0,
        "pad_dim_detected": False,
        "fcu": 25.0,
        "fy": 460.0,
        # Default structural grid: 2 bays in X × 2 bays in Y.
        # Keeping this in project state prevents first-load KeyError in the
        # Whole Building workspace before the engineer clicks Update Grid.
        "geometry": {
            "x_spacings": [4.0, 4.0],
            "y_spacings": [5.0, 5.0],
            "columns": [[i, j] for j in range(3) for i in range(3)],
        }
    }

# Persist calculation results so changing a control does not erase the last committed design.
if "design_results" not in st.session_state:
    st.session_state.design_results = {}
if "design_inputs" not in st.session_state:
    st.session_state.design_inputs = {}

def show_utilization(label: str, demand: float, capacity: float, unit: str = ""):
    """Visual utilization bar so an engineer can read 'how close' at a glance,
    not just pass/fail."""
    if capacity is None or capacity <= 0:
        return
    ratio = demand / capacity
    pct = min(ratio, 1.5)
    st.write(f"**{label} utilization:** {ratio:.0%}  ({demand:g} / {capacity:g} {unit})")
    st.progress(min(pct / 1.5, 1.0))
    if ratio > 1.0:
        st.caption("⚠️ Over capacity.")
    elif ratio > 0.95:
        st.caption("Close to capacity — little margin.")
    elif ratio < 0.5:
        st.caption("Well under capacity — section may be oversized for this demand.")


def stamp_settings(data: dict) -> dict:
    """Record which code/fcu/fy were active when this element was calculated,
    so later drift in the sidebar can be flagged instead of silently ignored."""
    data["_design_settings"] = {"code": code_choice, "f_cu": f_cu, "f_y": f_y}
    return data


def show_settings_drift_warning(data: dict):
    stamped = data.get("_design_settings") if data else None
    if not stamped:
        return
    current = {"code": code_choice, "f_cu": f_cu, "f_y": f_y}
    if stamped != current:
        st.warning(
            f"⚠️ These results were calculated with **{stamped['code']}, fcu={stamped['f_cu']}, fy={stamped['f_y']}**, "
            f"but the sidebar now shows **{current['code']}, fcu={current['f_cu']}, fy={current['f_y']}**. "
            "Recalculate this element to reflect the current settings before relying on it."
        )


def clear_result(key: str, label: str):
    if st.button(label, key=f"clear_{key}"):
        st.session_state.design_results.pop(key, None)
        st.rerun()

st.title("Integrated Structural Concrete Design Suite")

st.sidebar.header("Global Project Settings")

# BS 8110 Table 3.4 / EC2 Table 4.4N-style typical nominal cover by exposure
# condition. These are common, representative defaults for a first pass —
# always confirm the exact figure against the governing code clause and the
# project's specific exposure classification before construction.
_EXPOSURE_COVER_MM = {
    "Mild": 25.0,
    "Moderate": 35.0,
    "Severe": 40.0,
    "Very Severe": 50.0,
    "Extreme": 60.0,
}
_EC2_FCK_CLASSES = [16.0, 20.0, 25.0, 28.0, 30.0, 32.0, 35.0, 40.0, 45.0, 50.0]
_BS_FCU_CLASSES = [20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0]

with st.sidebar.form("global_settings_form"):
    code_input = st.selectbox("Design Code", ["BS8110", "Eurocode 2"], index=["BS8110", "Eurocode 2"].index(code_choice))
    if code_input == "Eurocode 2":
        fcu_input = st.selectbox(
            "Concrete Cylinder Strength, fck (N/mm²)", _EC2_FCK_CLASSES,
            index=_EC2_FCK_CLASSES.index(f_cu) if f_cu in _EC2_FCK_CLASSES else _EC2_FCK_CLASSES.index(25.0),
            help="Enter the real EN 1992-1-1 cylinder strength directly (e.g. 25 for class C25/30) — this is no longer approximated from a cube strength."
        )
    else:
        fcu_input = st.selectbox(
            "Concrete Cube Strength, fcu (N/mm²)", _BS_FCU_CLASSES,
            index=_BS_FCU_CLASSES.index(f_cu) if f_cu in _BS_FCU_CLASSES else _BS_FCU_CLASSES.index(25.0)
        )
    fy_input = st.number_input("Steel Yield Strength, fy (N/mm²)", value=float(f_y), step=10.0)

    st.markdown("**Concrete cover**")
    exposure_input = st.selectbox(
        "Exposure condition", list(_EXPOSURE_COVER_MM.keys()),
        index=list(_EXPOSURE_COVER_MM.keys()).index(st.session_state.global_settings.get("exposure", "Mild")),
        help="Sets a typical suggested cover for this condition — always confirm against the governing code clause for your specific project."
    )
    suggested_cover = _EXPOSURE_COVER_MM[exposure_input]
    cover_input = st.number_input(
        "Nominal cover (mm)", min_value=15.0, max_value=100.0,
        value=float(cover) if cover else suggested_cover, step=5.0,
        help=f"Suggested for {exposure_input} exposure: {suggested_cover:g}mm. Override if your project's cover requirement differs."
    )
    apply_settings = st.form_submit_button("Apply Project Settings", type="primary")
if apply_settings:
    st.session_state.global_settings.update({
        "code": code_input, "f_cu": fcu_input, "f_y": fy_input,
        "cover": cover_input, "exposure": exposure_input,
    })
    st.rerun()

code_choice = st.session_state.global_settings["code"]
f_cu = st.session_state.global_settings["f_cu"]
f_y = st.session_state.global_settings["f_y"]
cover = st.session_state.global_settings.get("cover", 25.0)

st.divider()

# ==========================================
# MODULE NAVIGATION
# ==========================================
modules = [
    "Project Dashboard",
    "Help & Troubleshooting",
    "CAD / PDF Drawing Importer",
    "Whole Building Automated Design",
    "Frame Analysis (Phase 2)",
    "Beam Design",
    "Column Design",
    "Pad Footing Design",
    "Slab Design",
    "Stair Design",
]

module = st.sidebar.selectbox("Design Module", modules, index=0)

with st.sidebar.expander("Report details (optional)"):
    st.session_state["project_name"] = st.text_input("Project name", value=st.session_state.get("project_name", ""))
    st.session_state["engineer_name"] = st.text_input("Engineer name", value=st.session_state.get("engineer_name", ""))

with st.sidebar.expander("💾 Save / load project"):
    import json

    def _build_project_save() -> str:
        from core.persistence import json_safe
        payload = {
            "global_settings": st.session_state.global_settings,
            "project_name": st.session_state.get("project_name", ""),
            "engineer_name": st.session_state.get("engineer_name", ""),
            "project_data": {k: v for k, v in st.session_state.project_data.items() if k != "pdf_images"},
            "design_results": st.session_state.design_results,
            "design_inputs": st.session_state.design_inputs,
        }
        return json.dumps(json_safe(payload), indent=2)

    st.download_button(
        "Save project (.json)", data=_build_project_save(),
        file_name=f"{(st.session_state.get('project_name') or 'rcc_project').replace(' ', '_')}.json",
        mime="application/json"
    )

    loaded_file = st.file_uploader("Load project (.json)", type=["json"], key="project_load_uploader")
    if loaded_file is not None:
        if st.button("Load into workspace", key="confirm_load_project"):
            try:
                loaded = json.loads(loaded_file.read())
                st.session_state.global_settings = loaded.get("global_settings", st.session_state.global_settings)
                st.session_state.project_name = loaded.get("project_name", "")
                st.session_state.engineer_name = loaded.get("engineer_name", "")
                st.session_state.project_data.update(loaded.get("project_data", {}))
                st.session_state.design_results = loaded.get("design_results", {})
                st.session_state.design_inputs = loaded.get("design_inputs", {})
                st.success("Project loaded. Switch modules in the sidebar to review it.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not load project file: {exc}")

st.sidebar.divider()
st.sidebar.caption("Calculations run only when you press a Calculate button. Visuals are optional and loaded on demand.")

# ==========================================
# 0. PROJECT DASHBOARD
# ==========================================
if module == "Project Dashboard":
    st.subheader("Project Dashboard")
    st.caption("A single-glance summary of every element calculated so far in this session. Nothing here is a new calculation — it just collects what you've already run.")

    results = st.session_state.design_results
    element_map = [
        ("beam", "Beam Design", lambda r: r),
        ("column", "Column Design", lambda r: r),
        ("footing", "Pad Footing Design", lambda r: r["result"]),
        ("slab", "Slab Design", lambda r: r["result"]),
        ("stair", "Stair Design", lambda r: r),
    ]

    any_results = any(results.get(k) for k, _, _ in element_map)
    if not any_results:
        st.info("No elements calculated yet. Use the sidebar to open a design module (Beam, Column, Footing, Slab or Stair), run a calculation, then come back here for the summary.")
    else:
        overall_counts = {"PASS": 0, "FAIL": 0, "WARNING": 0, "NOT CHECKED": 0}
        dash_cols = st.columns(len(element_map))
        for (key, title, extractor), col in zip(element_map, dash_cols):
            raw = results.get(key)
            with col:
                st.markdown(f"**{title}**")
                if raw is None:
                    st.caption("Not calculated yet.")
                    continue
                data = extractor(raw)
                audit = data.get("audit", {})
                checks = audit.get("checks", [])
                statuses = [c["status"] for c in checks]
                for s in statuses:
                    overall_counts[s] = overall_counts.get(s, 0) + 1
                n_pass = statuses.count("PASS")
                n_fail = statuses.count("FAIL")
                n_nc = statuses.count("NOT CHECKED") + statuses.count("WARNING")
                if not statuses:
                    st.warning("⚠️ No automated checks in this result — review manually.")
                    continue
                if n_fail > 0:
                    st.error(f"❌ {n_fail} failed check(s)")
                elif n_nc > 0:
                    st.warning(f"⚠️ {n_pass} passed, {n_nc} not checked")
                else:
                    st.success(f"✅ All {n_pass} checks passed")
                if key == "beam" and data.get("deflection_status") == "FAIL":
                    st.caption("Deflection screening also failing.")

        st.markdown("---")
        st.markdown("### Overall project status")
        total_checks = sum(overall_counts.values())
        if total_checks > 0:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Pass", overall_counts["PASS"])
            c2.metric("Fail", overall_counts["FAIL"])
            c3.metric("Warning", overall_counts["WARNING"])
            c4.metric("Not checked", overall_counts["NOT CHECKED"])
            if overall_counts["FAIL"] > 0:
                st.error("This project has at least one FAILED check — review the relevant module before proceeding.")
            elif overall_counts["NOT CHECKED"] > 0 or overall_counts["WARNING"] > 0:
                st.warning("This project has NOT CHECKED or WARNING items — it is not a completed design. Review the limitations listed in each module.")
            else:
                st.success("All calculated elements have every implemented check passing. Remember: this is still a preliminary aid, not a substitute for independent engineering review.")

        st.markdown("---")
        st.markdown("### Load path continuity")
        beam_r = results.get("beam")
        col_r = results.get("column")
        foot_r = results.get("footing")
        lp1, lp2, lp3 = st.columns(3)
        lp1.metric("Beam → Column reaction", f"{beam_r['reaction_gk_to_column_kN']:.1f} kN Gk" if beam_r else "—")
        lp2.metric("Column → Footing axial", f"{col_r['N_serv_to_footing_kN']:.1f} kN service" if col_r else "—")
        lp3.metric(
            "Footing size",
            f"{foot_r.get('pad_L', 0):.2f} × {foot_r.get('pad_B', 0):.2f} m" if foot_r else "—",
        )
        if beam_r and col_r and not st.session_state.get("_dash_note_shown"):
            pass
        st.caption(
            "Use the 🔗 'Pull from ... result' checkboxes inside Column Design and Pad Footing Design "
            "to carry these reactions through automatically instead of re-typing them."
        )

        st.markdown("---")
        st.markdown("### Combined project report")
        if st.button("Generate combined calc sheet for all calculated elements"):
            from core.reporter import StructuralReporter
            project_name = st.session_state.get("project_name", "")
            engineer_name = st.session_state.get("engineer_name", "")
            sections = []
            for key, title, extractor in element_map:
                raw = results.get(key)
                if raw is None:
                    continue
                data = extractor(raw)
                sections.append(StructuralReporter.generate_single_element_report(
                    title, data, code=code_choice, f_cu=f_cu, f_y=f_y,
                    project_name=project_name, engineer_name=engineer_name
                ))
            # Concatenate bodies of each standalone report into one document.
            import re as _re
            from html import escape as _html_escape
            bodies = []
            for html in sections:
                m = _re.search(r"<body>(.*)</body>", html, _re.DOTALL)
                if m:
                    bodies.append(m.group(1))
            combined = (
                "<!doctype html><html><head><meta charset='utf-8'>"
                "<title>Combined Project Calculation Report</title>"
                "<style>body{font-family:Arial,sans-serif;margin:32px;color:#25313b;line-height:1.45}"
                "h1{margin-bottom:4px} h2{border-bottom:2px solid #555;padding-bottom:5px}"
                "table{border-collapse:collapse;width:100%;margin:12px 0 22px}"
                "th,td{border:1px solid #bbb;padding:7px;text-align:left;font-size:13px}"
                "th{background:#eee} .badge{padding:3px 7px;border-radius:4px;font-weight:bold}"
                ".pass{background:#d9f2df} .fail{background:#ffd9d9} .nc{background:#ffeab5} .warn{background:#ffeab5}"
                ".notice{border:1px solid #c88;background:#fff5df;padding:14px;margin:15px 0}"
                "hr{margin:40px 0;border:none;border-top:3px double #999}</style></head><body>"
                f"<h1>Structural RCC Suite — Combined Project Report</h1>"
                f"<p><strong>Project:</strong> {_html_escape(project_name or '—')} | "
                f"<strong>Engineer:</strong> {_html_escape(engineer_name or '—')} | "
                f"<strong>Code:</strong> {_html_escape(code_choice)}</p>"
                + "<hr>".join(bodies) +
                "</body></html>"
            )
            st.download_button(
                "📄 Download combined project report (HTML)", data=combined,
                file_name="project_combined_calc_sheet.html", mime="text/html"
            )

# ==========================================
# 0.5 HELP & TROUBLESHOOTING
# ==========================================
elif module == "Help & Troubleshooting":
    from core.help_assistant import search as help_search, FAQ

    st.subheader("Help & Troubleshooting")
    st.caption(
        "This is a plain text search over the tool's own documentation and, if you've calculated anything "
        "this session, the exact audit messages and limitations already produced for your results. It is "
        "not an AI model and never generates a new engineering opinion — every answer either quotes this "
        "tool's own documentation or a message the calculation engine already produced."
    )
    query = st.text_input("Type a question about how to use the tool, what a status means, or why a result looks the way it does:", placeholder="e.g. why does my column show NOT CHECKED for slenderness?")

    if query:
        hits = help_search(query, design_results=st.session_state.get("design_results"))
        if hits:
            st.markdown("### Closest matches")
            for score, entry in hits:
                with st.container(border=True):
                    st.markdown(f"**{entry['question']}**")
                    st.write(entry["answer"])
        else:
            st.warning(
                "No close match found in the documentation or your current results. Try rephrasing, "
                "or browse the full list of topics below."
            )

    st.markdown("---")
    st.markdown("### Browse all topics")
    for entry in FAQ:
        with st.expander(entry["question"]):
            st.write(entry["answer"])

    if st.session_state.get("design_results"):
        st.markdown("---")
        st.markdown("### From your current session's results")
        st.caption("These are the exact NOT CHECKED / WARNING / FAIL messages already shown in your calculated elements, collected here for quick reference.")
        from core.help_assistant import _dynamic_entries_from_results
        dyn = _dynamic_entries_from_results(st.session_state.design_results)
        if dyn:
            for entry in dyn:
                with st.expander(entry["question"]):
                    st.write(entry["answer"])
        else:
            st.caption("Nothing calculated yet this session.")

# ==========================================
# 1. CAD (.DXF) & PDF DRAWING IMPORTER
# ==========================================
elif module == "CAD / PDF Drawing Importer":
    from pipeline.dxf_reader import CADReader
    from pipeline.pdf_reader import PDFPlanReader
    st.subheader("Architectural CAD (.DXF) & PDF Plan Reader")
    st.caption(
        "Values the parser can't confidently read are shown as **Not detected** — "
        "they are never silently filled with a guessed number. Confirm or correct "
        "every field below before it is used in a design module."
    )
    uploaded_file = st.file_uploader("Upload Drawing File (.dxf or .pdf)", type=["dxf", "pdf"])

    def _detected_field(label: str, value, unit: str, detected: bool, help_text: str = ""):
        col = st.container()
        if detected:
            col.metric(label, f"{value}{unit}")
            col.caption("✅ Detected from drawing — please still verify against the source sheet.")
        else:
            col.metric(label, "—")
            col.caption("⚠️ Not detected — enter manually below.")
        if help_text:
            col.caption(help_text)

    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        file_ext = uploaded_file.name.split('.')[-1].lower()

        if file_ext == "pdf":
            try:
                parsed = PDFPlanReader.extract_plan_parameters(file_bytes)
                images = PDFPlanReader.render_all_pages(file_bytes)

                st.session_state.project_data["has_drawing"] = True
                st.session_state.project_data["file_name"] = uploaded_file.name
                st.session_state.project_data["pdf_images"] = images
                st.session_state.project_data["pad_dim_detected"] = bool(parsed["pad_dim_detected"])

                st.success(f"PDF parsed ({parsed['total_pages']} page(s)). Review every field below before use.")

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    _detected_field("Grid Span X", parsed["spans_m"][0] if parsed["spans_detected"] else None, " m", parsed["spans_detected"])
                with c2:
                    _detected_field(
                        "Grid Span Y",
                        parsed["spans_m"][1] if parsed["spans_detected"] and len(parsed["spans_m"]) > 1 else None,
                        " m", parsed["spans_detected"] and len(parsed["spans_m"]) > 1
                    )
                with c3:
                    _detected_field("Slab Depth", parsed["detected_slab_thick"], " mm", parsed["slab_thick_detected"])
                with c4:
                    _detected_field("Pad Base", parsed["detected_pad_dim"], " mm", parsed["pad_dim_detected"])

                st.markdown("#### Confirm values before syncing to design modules")
                with st.form("pdf_confirm_form"):
                    fc1, fc2, fc3, fc4 = st.columns(4)
                    span_x_in = fc1.number_input("Span X (m)", min_value=1.0, max_value=20.0,
                                                  value=float(parsed["spans_m"][0]) if parsed["spans_detected"] else 4.0, step=0.1)
                    span_y_in = fc2.number_input("Span Y (m)", min_value=1.0, max_value=20.0,
                                                  value=float(parsed["spans_m"][1]) if parsed["spans_detected"] and len(parsed["spans_m"]) > 1 else 5.0, step=0.1)
                    slab_in = fc3.number_input("Slab thickness (mm)", min_value=75.0, max_value=500.0,
                                                value=float(parsed["detected_slab_thick"]) if parsed["slab_thick_detected"] else 150.0, step=5.0)
                    pad_in = fc4.number_input("Pad footing base (mm)", min_value=600.0, max_value=4000.0,
                                               value=float(parsed["detected_pad_dim"]) if parsed["pad_dim_detected"] else 1350.0, step=10.0)
                    confirmed = st.form_submit_button("Sync confirmed values to design modules")
                    if confirmed:
                        st.session_state.project_data["span_x"] = span_x_in
                        st.session_state.project_data["span_y"] = span_y_in
                        st.session_state.project_data["slab_thick"] = slab_in
                        st.session_state.project_data["pad_dim"] = pad_in
                        if parsed["fcu_detected"]:
                            st.session_state.project_data["fcu"] = parsed["fcu"]
                        st.success("Confirmed values synced. Nothing was assumed on your behalf.")

                st.markdown("### Sheet Preview")
                preview_page = st.selectbox("Sheet Preview", range(len(images)), format_func=lambda x: f"Page {x+1}")
                st.image(images[preview_page], use_container_width=True)

            except Exception as e:
                st.error(f"Error reading PDF: {e}")

        elif file_ext == "dxf":
            try:
                dxf_info = CADReader.parse_dxf_stream(file_bytes)
                st.session_state.project_data["has_drawing"] = True
                st.session_state.project_data["file_name"] = uploaded_file.name

                if dxf_info["unit_confidence"] == "guessed":
                    st.warning(
                        f"⚠️ Drawing units: {dxf_info['unit_source']}. Detected spans below are a best-effort "
                        "guess and must be checked against the drawing's title block."
                    )
                else:
                    st.caption(f"Drawing units confirmed from {dxf_info['unit_source']}.")

                x_spans = dxf_info.get("x_spans", [])
                y_spans = dxf_info.get("y_spans", [])
                c1, c2, c3 = st.columns(3)
                with c1:
                    _detected_field("Grid Span X", x_spans[0] if x_spans else None, " m", bool(x_spans))
                with c2:
                    _detected_field("Grid Span Y", y_spans[0] if y_spans else None, " m", bool(y_spans))
                with c3:
                    st.metric("Columns / blocks found", dxf_info["total_columns_found"])
                st.caption(dxf_info.get("detection_note", ""))

                st.markdown("#### Confirm values before syncing to design modules")
                with st.form("dxf_confirm_form"):
                    fc1, fc2 = st.columns(2)
                    span_x_in = fc1.number_input("Span X (m)", min_value=1.0, max_value=20.0,
                                                  value=float(x_spans[0]) if x_spans else 4.0, step=0.1)
                    span_y_in = fc2.number_input("Span Y (m)", min_value=1.0, max_value=20.0,
                                                  value=float(y_spans[0]) if y_spans else 5.0, step=0.1)
                    confirmed = st.form_submit_button("Sync confirmed values to design modules")
                    if confirmed:
                        st.session_state.project_data["span_x"] = span_x_in
                        st.session_state.project_data["span_y"] = span_y_in
                        st.success("Confirmed values synced. Nothing was assumed on your behalf.")
            except Exception as e:
                st.error(f"Error reading DXF: {e}")

# ==========================================
# 2. WHOLE BUILDING AUTOMATION
# ==========================================
elif module == "Whole Building Automated Design":
    from pipeline.building import BuildingModel
    from core.reporter import StructuralReporter
    st.subheader("Whole Building — Gravity Design Workspace")
    st.caption("The geometry editor below is the first step toward a true engineer-defined structural model. Geometry drives the structural 3D preview now; the current automated gravity calculations still use a representative internal bay and are clearly labelled as such.")

    st.markdown("###  Structural Grid & Column Layout")
    geom = st.session_state.project_data.get("geometry", {})
    gx_default = ", ".join(str(v) for v in geom.get("x_spacings", [4.0, 4.0]))
    gy_default = ", ".join(str(v) for v in geom.get("y_spacings", [5.0, 5.0]))
    with st.form("geometry_form"):
        gc1, gc2, gc3 = st.columns([2, 2, 1])
        with gc1:
            x_text = st.text_input("X grid spacings (m)", value=gx_default, help="Enter each bay width from left to right, e.g. 4, 4, 5 creates 4 m, 4 m and 5 m bays.")
        with gc2:
            y_text = st.text_input("Y grid spacings (m)", value=gy_default, help="Enter each bay depth from front to back, e.g. 5, 5 creates two 5 m bays.")
        with gc3:
            update_geometry = st.form_submit_button("Update Grid", type="primary")
    if update_geometry:
        try:
            xs = parse_spacings(x_text)
            ys = parse_spacings(y_text)
            cols = [[i, j] for j in range(len(ys) + 1) for i in range(len(xs) + 1)]
            st.session_state.project_data["geometry"] = {"x_spacings": list(xs), "y_spacings": list(ys), "columns": cols}
            st.success(f"Grid updated: {len(xs)+1} X-lines × {len(ys)+1} Y-lines, {len(cols)} column positions available.")
            st.rerun()
        except (ValueError, TypeError) as exc:
            st.error(f"Grid error: {exc}")

    geom = st.session_state.project_data["geometry"]
    geometry = GridGeometry(tuple(geom["x_spacings"]), tuple(geom["y_spacings"]), tuple(tuple(c) for c in geom["columns"]))
    options = [
        (i, j, f"C{i+1}{j+1} — X {geometry.x_coords[i]:g} m, Y {geometry.y_coords[j]:g} m")
        for j in range(len(geometry.y_coords)) for i in range(len(geometry.x_coords))
    ]
    option_labels = [x[2] for x in options]
    current_labels = [label for i, j, label in options if [i, j] in geom["columns"]]
    selected_labels = st.multiselect("Columns present at grid intersections", option_labels, default=current_labels, help="Remove a column to create an opening/irregular layout. Adjacent selected columns automatically define beams in the structural preview.")
    selected_set = {tuple((i, j)) for i, j, label in options if label in selected_labels}
    st.session_state.project_data["geometry"]["columns"] = [list(c) for c in sorted(selected_set)]
    st.caption(f"Defined geometry: {len(geometry.x_coords)} X-lines × {len(geometry.y_coords)} Y-lines, {len(selected_set)} columns, {len(GridGeometry(geometry.x_spacings, geometry.y_spacings, tuple(selected_set)).beam_edges)} beam segments per level.")

    with st.form("whole_building_inputs"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            grid_x = st.number_input("Representative Bay X (m)", value=float(st.session_state.project_data["span_x"]), step=0.25, help="Used by the current representative-bay gravity calculation. The structural grid above is used by the geometry preview.")
        with col2:
            grid_y = st.number_input("Representative Bay Y (m)", value=float(st.session_state.project_data["span_y"]), step=0.25, help="Used by the current representative-bay gravity calculation. The structural grid above is used by the geometry preview.")
        with col3:
            num_floors = st.number_input("Building Storeys Above Ground", value=2, min_value=1, max_value=25, step=1, help="Use 1 for a bungalow/single-storey building, 2 for ground + one upper storey, 3 for ground + two upper storeys, etc.")
        with col4:
            qa_val = st.number_input("Soil Bearing Capacity (kN/m²)", value=150.0, step=10.0)
        ld1, ld2 = st.columns(2)
        with ld1:
            slab_finish_gk = st.number_input("Slab Finishes / Partitions Gk (kN/m²)", value=1.5, min_value=0.0, step=0.25)
        with ld2:
            slab_live_qk = st.number_input("Slab Imposed Qk (kN/m²)", value=2.0, min_value=0.0, step=0.5)
        wh1, wh2, wh3 = st.columns(3)
        with wh1:
            wall_h = st.number_input("Wall Height (m)", value=2.8, min_value=0.0, step=0.1)
        with wh2:
            wall_t = st.number_input("Wall Thickness (m)", value=0.20, min_value=0.0, step=0.01)
        with wh3:
            wall_uw = st.number_input("Wall Unit Weight (kN/m³)", value=18.0, min_value=0.0, step=1.0)
        st.caption(f"Derived wall line load = {wall_h * wall_t * wall_uw:.2f} kN/m (from the wall geometry above).")
        market_rate = st.number_input("Current Steel Market Rate (KES / Tonne)", value=145000.0, step=5000.0, format="%.2f")
        run_building = st.form_submit_button("Calculate Whole Building", type="primary")
    show_visuals = st.checkbox("Show interactive diagrams and 3D model", value=False)
    if run_building:
        b_model = BuildingModel(
            bay_lx=grid_x, bay_ly=grid_y, num_storeys=num_floors,
            h_slab=st.session_state.project_data["slab_thick"],
            q_allowable=qa_val, code=code_choice, f_cu=f_cu, f_y=f_y,
            slab_gk_finishes=slab_finish_gk, slab_qk_live=slab_live_qk,
            wall_height=wall_h, wall_unit_weight=wall_uw, wall_thick=wall_t
        )
        full_res = b_model.run_full_design()
        bbs_rows = b_model.bbs_rows(full_res)
        cost_data = StructuralReporter.calculate_tonnage_and_cost(full_res, cost_per_tonne_kes=market_rate, bbs_rows=bbs_rows)
        st.session_state.design_results["whole_building"] = {"full_res": full_res, "bbs_rows": bbs_rows, "cost_data": cost_data, "market_rate": market_rate, "grid_x": grid_x, "grid_y": grid_y, "num_floors": int(num_floors), "slab_gk": slab_finish_gk, "slab_qk": slab_live_qk, "wall_h": wall_h, "wall_t": wall_t, "wall_uw": wall_uw, "qa": qa_val}
    saved_building = st.session_state.design_results.get("whole_building")
    if saved_building is None:
        st.info("Enter or review the project inputs, then click **Calculate Whole Building**.")
        st.stop()
    clear_result("whole_building", "Clear Calculated Building Result")
    full_res = saved_building["full_res"]
    bbs_rows = saved_building["bbs_rows"]
    cost_data = saved_building["cost_data"]
    market_rate = saved_building["market_rate"]
    grid_x = saved_building["grid_x"]
    grid_y = saved_building["grid_y"]
    num_floors = saved_building["num_floors"]
    show_visuals = show_visuals
    overall_status = full_res["summary"]["overall_status"]
    if overall_status == "FAIL":
        st.error("Engineering status: FAIL — at least one implemented check fails.")
    elif overall_status == "NOT CHECKED":
        st.warning("Engineering status: NOT CHECKED — some verification checks are not implemented sufficiently to claim code compliance.")
    elif overall_status == "WARNING":
        st.warning("Engineering status: WARNING — review the stated applicability/detailing warnings.")
    else:
        st.success("All implemented checks passed; review the stated limitations before use.")
    with st.expander("What does NOT CHECKED mean?", expanded=False):
        st.write("NOT CHECKED does not mean the member has failed. It means this version has not implemented enough of that verification to claim compliance. The engineer must complete the missing check independently.")

    st.markdown("###  Automated Load Path Summary")
    lp1, lp2, lp3, lp4 = st.columns(4)
    with lp1:
        st.info(f"**1. Slab (Panel 1)**\n- Msx: `{full_res['slab']['Msx_pos']} kNm/m`\n- Bottom Rebar: `{full_res['slab']['rebar_sx']['description']}`")
    with lp2:
        st.info(f"**2. Beam (RCC41)**\n- Support Vu: `{full_res['beam']['V_support_kN']} kN`\n- Bottom Rebar: `{full_res['beam']['span_bars']['description']}`")
    with lp3:
        st.info(f"**3. Column (RCC51)**\n- {('NEd' if code_choice == 'Eurocode 2' else 'Nu')}: `{full_res['column']['N_ult_total_kN']} kN`\n- Main Rebar: `{full_res['column']['main_rebar']['description']}`")
    with lp4:
        pad_L, pad_B, q_act = full_res["pad_size"]
        st.info(f"**4. Pad Footing (RCC81)**\n- Size: `{pad_L:.2f}m × {pad_B:.2f}m`\n- Mat: `{full_res['footing']['rebar']['description']}`")

    warnings = StructuralReporter.audit_detailing(full_res)
    if warnings:
        st.markdown("###  Detailing & Code Rule Checks")
        for w in warnings:
            if w["level"] == "warning":
                st.warning(f"**{w['element']}:** {w['message']}")
            else:
                st.info(f"**{w['element']}:** {w['message']}")

    st.markdown("---")
    st.subheader("Reinforcement Steel Quantity & Cost Estimate")
    st.caption("Preliminary procurement estimate based on the current representative-bay BBS. Review bar lengths, laps, anchorage, curtailment, wastage and final detailing before ordering steel.")

    with st.expander("Estimate assumptions", expanded=True):
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            market_rate = st.number_input("Steel rate (KES / tonne)", value=float(market_rate), min_value=0.0, step=5000.0, format="%.2f", key="whole_steel_rate")
        with cc2:
            wastage_pct = st.number_input("Procurement allowance / wastage (%)", value=5.0, min_value=0.0, max_value=20.0, step=0.5, format="%.1f", key="whole_steel_wastage")
        with cc3:
            st.metric("Base BBS quantity", f"{cost_data.get('total_tonnes', 0.0):.3f} t")

    # Recalculate the commercial estimate from the engineer's current rate and allowance.
    cost_data = StructuralReporter.calculate_tonnage_and_cost(
        full_res, cost_per_tonne_kes=market_rate, bbs_rows=bbs_rows, wastage_pct=wastage_pct
    )
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("BBS steel", f"{cost_data['total_tonnes']:.3f} t")
    t2.metric("Procurement quantity", f"{cost_data['procurement_tonnes']:.3f} t")
    t3.metric("Steel rate", f"KES {market_rate:,.0f} / t")
    t4.metric("Estimated steel cost", f"KES {cost_data['estimated_cost_kes']:,.2f}")

    if cost_data["breakdown_kg"]:
        st.markdown("**Steel weight by diameter**")
        rows = [{"Diameter": f"Y{d}", "BBS weight (kg)": kg, "Share (%)": round(100 * kg / cost_data["total_kg"], 1) if cost_data["total_kg"] else 0.0} for d, kg in cost_data["breakdown_kg"].items()]
        st.dataframe(rows, use_container_width=True, hide_index=True)

    if cost_data["element_breakdown_kg"]:
        st.markdown("**Steel weight by structural element**")
        element_rows = [{"Element": e, "BBS weight (kg)": kg, "Share (%)": round(100 * kg / cost_data["total_kg"], 1) if cost_data["total_kg"] else 0.0} for e, kg in cost_data["element_breakdown_kg"].items()]
        st.dataframe(element_rows, use_container_width=True, hide_index=True)

    st.info(f"BBS weight: {cost_data['total_kg']:,.1f} kg + {wastage_pct:.1f}% allowance ({cost_data['wastage_kg']:,.1f} kg) = {cost_data['procurement_kg']:,.1f} kg procurement quantity.")
    st.caption(cost_data["quantity_basis"])

    st.markdown("---")
    st.subheader("Export Engineering Deliverables")
    # Recreate the model only for export generation; calculation results are already cached in session state.
    b_model = BuildingModel(
        bay_lx=grid_x, bay_ly=grid_y, num_storeys=num_floors,
        h_slab=st.session_state.project_data["slab_thick"],
        q_allowable=saved_building["qa"],
        code=code_choice, f_cu=f_cu, f_y=f_y,
        slab_gk_finishes=saved_building["slab_gk"],
        slab_qk_live=saved_building["slab_qk"],
        wall_height=saved_building["wall_h"],
        wall_unit_weight=saved_building["wall_uw"],
        wall_thick=saved_building["wall_t"]
    )
    exp1, exp2 = st.columns(2)
    with exp1:
        excel_bytes = b_model.generate_bbs_excel(full_res)
        st.download_button(
            label="Download Full BBS Schedule (.xlsx)",
            data=excel_bytes,
            file_name="Building_Reinforcement_BBS.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    with exp2:
        report_html = StructuralReporter.generate_html_report(full_res, code=code_choice, f_cu=f_cu, f_y=f_y)
        st.download_button(
            label="Download Calculation Booklet (.html)",
            data=report_html,
            file_name="Structural_Calculation_Report.html",
            mime="text/html"
        )

    # Keep the interactive 3D viewer at the bottom of the workflow so it cannot interrupt
    # normal page scrolling while the engineer reviews calculations and deliverables.
    if show_visuals:
        from core.bay_frame_3d import BayFrame3D
        from core.visualizer import SectionVisualizer
        st.markdown("---")
        st.markdown("### Parametric Structural Section Drawings")
        st.caption("Lightweight section schematics for visual review of the selected structural elements.")
        vcol1, vcol2, vcol3 = st.columns(3)
        with vcol1:
            fig_b = SectionVisualizer.draw_beam_section(b=200, h=450, cover=25, num_top=2, dia_top=16, num_bot=2, dia_bot=16)
            st.plotly_chart(fig_b, use_container_width=True)
        with vcol2:
            fig_c = SectionVisualizer.draw_column_section(b=200, h=200, cover=25, num_bars=4, bar_dia=16)
            st.plotly_chart(fig_c, use_container_width=True)
        with vcol3:
            fig_f = SectionVisualizer.draw_footing_elevation(pad_L_m=pad_L, pad_h_mm=300, col_dim_mm=200)
            st.plotly_chart(fig_f, use_container_width=True)

        # The interactive 3D chart is shown inside a modal dialog, not inline in
        # the page. 3D (WebGL) canvases can capture mouse-wheel scroll and block
        # it from reaching the page even with scrollZoom disabled — a known
        # browser/Plotly interaction issue, not something fixable by chart
        # config alone. A dialog with an explicit Close button guarantees an
        # escape route instead of relying on the mouse landing in exactly the
        # right spot to resume scrolling.
        st.markdown("---")
        st.subheader("Structural 3D Preview")
        st.caption("Optional interactive structural schematic, shown in a popup window so it never interferes with scrolling the rest of the page.")

        @st.dialog("Structural 3D Preview", width="large")
        def _show_3d_preview():
            st.caption("Drag to rotate, right-click-drag or pinch to zoom. Close this window to return to the page — page scrolling is never affected while this is closed.")
            geometry = GridGeometry(
                tuple(st.session_state.project_data["geometry"]["x_spacings"]),
                tuple(st.session_state.project_data["geometry"]["y_spacings"]),
                tuple(tuple(c) for c in st.session_state.project_data["geometry"]["columns"]),
            )
            fig_3d = BayFrame3D.plot_3d_geometry(geometry=geometry, num_storeys=int(num_floors))
            st.plotly_chart(
                fig_3d, use_container_width=True,
                config={"scrollZoom": False, "displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
            )
            if st.button("Close"):
                st.rerun()

        if st.button("🧊 Open interactive 3D preview"):
            _show_3d_preview()

# ==========================================
# 2.5 FRAME ANALYSIS (PHASE 2)
# ==========================================
elif module == "Frame Analysis (Phase 2)":
    import pandas as pd
    from dataclasses import asdict
    from pipeline.frame import FrameBuilding

    st.subheader("3-D Frame Analysis — Gravity + Wind Screening")
    st.caption(
        "Linear-elastic 3-D frame built from the structural grid above. Columns and beams are "
        "rigid-jointed, bases are fixed, slab loads are distributed by tributary width, and wind "
        "is applied as equivalent nodal floor loads. This is a screening model, not a full "
        "seismic/soil-structure/non-linear analysis."
    )

    geom = st.session_state.project_data.get("geometry", {})
    if not geom.get("columns"):
        st.error("Define at least one column in the Whole Building geometry first.")
        st.stop()

    with st.form("frame_inputs"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            frame_storeys = st.number_input("Frame storeys", 1, 20, 3, 1)
        with c2:
            frame_height = st.number_input("Storey height (m)", 2.5, 6.0, 3.0, 0.1)
        with c3:
            frame_slab_gk = st.number_input("Slab Gk (kN/m²)", 0.0, 20.0, 4.5, 0.25)
        with c4:
            frame_slab_qk = st.number_input("Slab Qk (kN/m²)", 0.0, 20.0, 2.0, 0.25)
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            frame_beam_b = st.number_input("Beam width (mm)", 150.0, 800.0, 250.0, 25.0)
        with s2:
            frame_beam_h = st.number_input("Beam depth (mm)", 250.0, 1500.0, 500.0, 25.0)
        with s3:
            frame_col_b = st.number_input("Column width (mm)", 200.0, 1200.0, 300.0, 25.0)
        with s4:
            frame_col_h = st.number_input("Column depth (mm)", 200.0, 1200.0, 300.0, 25.0)
        w1, w2, w3, w4 = st.columns(4)
        with w1:
            frame_wind = st.number_input("Basic wind velocity (m/s)", 15.0, 60.0, 30.0, 1.0)
        with w2:
            frame_terrain = st.selectbox("Terrain", ["suburban", "open", "urban"], index=0)
        with w3:
            frame_wall = st.number_input("Wall load on beams (kN/m)", 0.0, 50.0, 0.0, 1.0)
        with w4:
            drift_choice = st.selectbox("Drift limit", ["H/300", "H/400", "H/500"], index=1)
        run_frame = st.form_submit_button("Run Frame Analysis", type="primary")

    drift_limit = {"H/300": 1 / 300, "H/400": 1 / 400, "H/500": 1 / 500}[drift_choice]
    if run_frame:
        try:
            fb = FrameBuilding(
                geom["x_spacings"], geom["y_spacings"], geom["columns"],
                num_storeys=int(frame_storeys), storey_height_m=frame_height,
                slab_gk_kpa=frame_slab_gk, slab_qk_kpa=frame_slab_qk,
                beam_b_mm=frame_beam_b, beam_h_mm=frame_beam_h,
                col_b_mm=frame_col_b, col_h_mm=frame_col_h,
                f_ck_mpa=f_cu, code=code_choice,
                wind_speed_m_s=frame_wind, terrain=frame_terrain,
                wall_load_kn_m=frame_wall, drift_limit=drift_limit,
            )
            res = fb.analyse()
            st.session_state.design_results["frame"] = {
                "storeys": res.storeys,
                "storey_height_m": res.storey_height_m,
                "nodes": len(res.model.nodes),
                "members": len(res.model.members),
                "max_drift_x": res.max_drift_x,
                "max_drift_y": res.max_drift_y,
                "drift_limit": res.drift_limit,
                "max_translation_x_mm": res.max_translation_x_mm,
                "max_translation_y_mm": res.max_translation_y_mm,
                "base_shear_x_kN": res.base_shear_x_kN,
                "base_shear_y_kN": res.base_shear_y_kN,
                "applied_wind_x_kN": res.applied_wind_x_kN,
                "applied_wind_y_kN": res.applied_wind_y_kN,
                "wind": res.wind,
                "warnings": list(res.warnings),
                "combinations": [asdict(c) for c in res.combinations],
                "envelopes": [asdict(e) for e in res.envelopes],
            }
            st.success("Frame analysis complete.")
        except Exception as exc:
            st.error(f"Frame analysis failed: {exc}")

    saved = st.session_state.design_results.get("frame")
    if saved is None:
        st.info("Review the frame inputs and click **Run Frame Analysis**.")
        st.stop()

    st.markdown(f"### Frame summary — {saved['storeys']} storeys × {saved['storey_height_m']} m")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Nodes / members", f"{saved['nodes']} / {saved['members']}")
    m2.metric("Max drift X", f"{saved['max_drift_x']:.5f}", delta=f"limit {saved['drift_limit']:.5f}", delta_color="off")
    m3.metric("Max drift Y", f"{saved['max_drift_y']:.5f}")
    m4.metric("Max lateral displacement", f"{saved['max_translation_x_mm']:.1f} mm")

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Base shear X", f"{saved['base_shear_x_kN']:.1f} kN")
    b2.metric("Applied wind X (unfactored)", f"{saved['applied_wind_x_kN']:.1f} kN")
    b3.metric("Base shear Y", f"{saved['base_shear_y_kN']:.1f} kN")
    b4.metric("Applied wind Y (unfactored)", f"{saved['applied_wind_y_kN']:.1f} kN")

    if saved["max_drift_x"] > saved["drift_limit"] or saved["max_drift_y"] > saved["drift_limit"]:
        st.error("Drift exceeds the selected screening limit — increase stiffness or revise the lateral system.")
    else:
        st.success("Drift is within the selected screening limit under the analysed combinations.")
    for warning in saved.get("warnings", []):
        st.warning(warning)

    st.markdown("### Load combinations")
    combo_rows = [{"Combination": c["name"], "Kind": c["kind"],
                   **{f"γ{k}": v for k, v in c["factors"].items()}}
                  for c in saved["combinations"]]
    st.dataframe(pd.DataFrame(combo_rows), use_container_width=True, hide_index=True)
    st.caption("Wind combinations are analysed in X and Y separately; the member envelope covers both directions.")

    st.markdown("### Member action envelope")
    env_df = pd.DataFrame(saved["envelopes"])
    if not env_df.empty:
        kind_filter = st.multiselect("Member type", ["beam", "column"], default=["beam", "column"])
        view = env_df[env_df["kind"].isin(kind_filter)].copy()
        view = view.sort_values("Mz_max_kNm", ascending=False)
        st.dataframe(
            view.rename(columns={
                "label": "Member", "kind": "Type", "N_max_kN": "N max (kN)",
                "Mz_max_kNm": "Mz max (kNm)", "My_max_kNm": "My max (kNm)",
                "Vy_max_kN": "Vy max (kN)", "Vz_max_kN": "Vz max (kN)",
            })[["Member", "Type", "N max (kN)", "Mz max (kNm)", "My max (kNm)", "Vy max (kN)", "Vz max (kN)"]],
            use_container_width=True, hide_index=True,
        )
        st.caption("End-force envelope across ULS/SLS combinations. Beam design still uses the Continuous Beam module; column design can be run with the envelope moments and axial loads.")
    st.caption("Frame scope: rigid joints, fixed bases, no soil-structure interaction, no seismic action, no floor-diaphragm flexibility, no second-order frame effects.")

# ==========================================
# 3. CONTINUOUS BEAM (RCC41)
# ==========================================
elif module == "Beam Design":
    from elements.beam import ContinuousBeam
    from core.visualizer import SectionVisualizer
    from core.diagrams import DiagramPlotter
    import pandas as pd

    st.subheader("Continuous Beam Design (Benchmarked against RCC41.xls)")
    st.caption(
        "Each span below can have its own length, width, depth, and loading — edit the table freely, "
        "add or remove rows for however many spans your beam actually has. The analysis is a real matrix "
        "(slope-deflection) solution with pattern loading across spans, not a lookup table limited to equal spans."
    )

    if "beam_span_table" not in st.session_state:
        st.session_state.beam_span_table = pd.DataFrame([
            {"Length (m)": float(st.session_state.project_data["span_y"]), "Width bw (mm)": 200.0, "Depth h (mm)": 450.0,
             "Flange width (mm)": 0.0, "Flange thickness (mm)": 0.0,
             "Other Dead Gk (kN/m)": 12.0, "Imposed Qk (kN/m)": 6.0},
            {"Length (m)": float(st.session_state.project_data["span_y"]), "Width bw (mm)": 200.0, "Depth h (mm)": 450.0,
             "Flange width (mm)": 0.0, "Flange thickness (mm)": 0.0,
             "Other Dead Gk (kN/m)": 12.0, "Imposed Qk (kN/m)": 6.0},
        ])

    span_table = st.data_editor(
        st.session_state.beam_span_table, num_rows="dynamic", use_container_width=True,
        key="beam_span_editor",
        column_config={
            "Length (m)": st.column_config.NumberColumn(min_value=0.5, max_value=30.0, step=0.25, required=True),
            "Width bw (mm)": st.column_config.NumberColumn(min_value=100.0, max_value=1000.0, step=25.0, required=True),
            "Depth h (mm)": st.column_config.NumberColumn(min_value=150.0, max_value=2000.0, step=25.0, required=True),
            "Flange width (mm)": st.column_config.NumberColumn(min_value=0.0, step=50.0, help="0 = rectangular beam; otherwise an effective T-beam flange width (e.g. slab tributary width)."),
            "Flange thickness (mm)": st.column_config.NumberColumn(min_value=0.0, step=10.0, help="Slab thickness for a T-beam; 0 = rectangular beam."),
            "Other Dead Gk (kN/m)": st.column_config.NumberColumn(min_value=0.0, step=1.0, required=True),
            "Imposed Qk (kN/m)": st.column_config.NumberColumn(min_value=0.0, step=1.0, required=True),
        },
    )
    # Backward compatibility for a session created before the T-beam columns
    # were added.
    if "Flange width (mm)" not in span_table.columns:
        span_table["Flange width (mm)"] = 0.0
    if "Flange thickness (mm)" not in span_table.columns:
        span_table["Flange thickness (mm)"] = 0.0
    st.session_state.beam_span_table = span_table

    with st.form("beam_wall_inputs"):
        st.caption("Wall load (applied uniformly to every span, if present):")
        bl1, bl2, bl3 = st.columns(3)
        with bl1:
            wall_h = st.number_input("Wall Height (m)", value=2.8, min_value=0.0, step=0.1)
        with bl2:
            wall_t = st.number_input("Wall Thickness (m)", value=0.20, min_value=0.0, step=0.01)
        with bl3:
            wall_uw = st.number_input("Wall Unit Weight (kN/m³)", value=18.0, min_value=0.0, step=1.0)
        run_beam = st.form_submit_button("Calculate Beam", type="primary")
    show_beam_visuals = st.checkbox("Show beam section and force diagrams", value=False)

    if run_beam:
        table = span_table.dropna()
        if len(table) == 0:
            st.error("Add at least one span row before calculating.")
            st.stop()
        lengths = table["Length (m)"].tolist()
        widths = table["Width bw (mm)"].tolist()
        depths = table["Depth h (mm)"].tolist()
        flange_widths = table["Flange width (mm)"].tolist()
        flange_thicknesses = table["Flange thickness (mm)"].tolist()
        gks = table["Other Dead Gk (kN/m)"].tolist()
        qks = table["Imposed Qk (kN/m)"].tolist()
        try:
            beam = ContinuousBeam(
                spans=lengths, b_w=widths, h_overall=depths, cover=cover,
                gk_slab=gks, qk_slab=qks,
                flange_width=flange_widths, flange_thickness=flange_thicknesses,
                wall_height=wall_h, wall_thick=wall_t, wall_unit_weight=wall_uw,
                f_cu=f_cu, f_y=f_y, code=code_choice,
            )
            st.session_state.design_results["beam"] = stamp_settings(beam.design_beam())
            st.session_state.design_inputs["beam"] = dict(
                spans=lengths, b_w=widths, h_overall=depths, cover=cover,
                gk_slab=gks, qk_slab=qks,
                flange_width=flange_widths, flange_thickness=flange_thicknesses,
                wall_height=wall_h, wall_thick=wall_t, wall_unit_weight=wall_uw,
                f_cu=f_cu, f_y=f_y, code=code_choice,
            )
        except ValueError as exc:
            st.error(f"Input error: {exc}")
            st.stop()

    b_res = st.session_state.design_results.get("beam")
    if b_res is None:
        st.info("Review the span table above, then click **Calculate Beam**.")
        st.stop()

    clear_result("beam", "Clear Calculated Beam Result")
    show_settings_drift_warning(b_res)
    beam_inputs = st.session_state.design_inputs.get("beam", {})

    st.markdown(f"#### Governing span (largest reinforcement demand, of {b_res['num_spans']})")
    col_data, col_plot = st.columns([1, 1])
    with col_data:
        st.metric("Total Ultimate Load (w), governing span", f"{b_res['w_ult_kN_m']} kN/m")
        st.metric("Span Moment (M_span)", f"{b_res['M_span_kNm']} kNm")
        st.metric("Support Moment (M_supp)", f"{b_res['M_support_kNm']} kNm")
        st.success(f"**Bottom Steel (Span):** {b_res['span_bars']['description']}")
        st.success(f"**Top Steel (Support):** {b_res['supp_bars']['description']}")
        st.write(f"**Shear Links:** `{b_res['link_schedule']}`")
        st.write(
            f"**Crack width (quasi-permanent):** {b_res.get('crack_status', 'NOT CHECKED')} — "
            f"governing span wk = {b_res.get('spans_detail', [{}])[0].get('wk_span_mm', '—')} mm"
        )
        if b_res.get("deflection_status") in ("PASS", "FAIL"):
            span_d_msg = f"span/d = {b_res['actual_span_d']} vs allowable {b_res['allowable_span_d']}"
            if b_res["deflection_status"] == "PASS":
                st.success(f"**Deflection screening: PASS** — {span_d_msg}")
            else:
                st.error(f"**Deflection screening: FAIL** — {span_d_msg} (increase depth or reduce span)")
                st.caption("💡 Try increasing the governing span's depth, or splitting it with an intermediate support.")
                if st.button("🔁 Retry with governing span depth +50mm", key="retry_beam_depth"):
                    saved_inputs = dict(st.session_state.design_inputs.get("beam", {}))
                    # Bump every span's depth by 50mm — simplest safe retry that always helps the governing span too.
                    h_list = list(saved_inputs.get("h_overall", [450.0]))
                    saved_inputs["h_overall"] = [h + 50.0 for h in h_list]
                    retry_beam = ContinuousBeam(**saved_inputs)
                    st.session_state.design_results["beam"] = stamp_settings(retry_beam.design_beam())
                    st.session_state.design_inputs["beam"] = saved_inputs
                    st.rerun()

        st.markdown("#### Per-span breakdown")
        detail_rows = [{
            "Span": s["span_index"] + 1, "Length (m)": s["length_m"], "b×h (mm)": f"{s['b_w']:.0f}×{s['h_overall']:.0f}",
            "Section": s.get("section_type", "rectangular"),
            "M span (kNm)": s["M_span_kNm"], "M support (kNm)": s["M_support_kNm"],
            "Bottom steel": s["span_bars"]["description"], "Top steel": s["supp_bars"]["description"],
            "Links": s["link_schedule"], "Shear": s["shear_status"], "Deflection": s["deflection_status"],
        } for s in b_res["spans_detail"]]
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

        show_audit(b_res.get("audit", {}), "Beam verification")
        download_calc_sheet("Beam Design", b_res, "beam")
        if beam_inputs:
            from core.dxf_export import generate_beam_dxf
            gov = max(b_res["spans_detail"], key=lambda s: s["span_bars"]["As_prov"] + s["supp_bars"]["As_prov"])
            dxf_bytes = generate_beam_dxf(
                b_res, b_w=gov["b_w"], h_overall=gov["h_overall"], cover=beam_inputs.get("cover", cover),
                code=code_choice, project_name=st.session_state.get("project_name", ""),
                engineer_name=st.session_state.get("engineer_name", ""),
                flange_width=gov.get("flange_width_mm", 0.0),
                flange_thickness=gov.get("flange_thickness_mm", 0.0),
            )
            download_dxf("Beam Design", dxf_bytes, "beam")
            st.caption("The downloaded drawing shows the governing span's section — see the per-span table above for every span's own dimensions and reinforcement.")

    if show_beam_visuals:
        gov = max(b_res["spans_detail"], key=lambda s: s["span_bars"]["As_prov"] + s["supp_bars"]["As_prov"])
        with col_plot:
            n_bot = gov['span_bars'].get('bar_count', 2)
            d_bot = gov['span_bars'].get('bar_diameter', 16)
            n_top = gov['supp_bars'].get('bar_count', 2)
            d_top = gov['supp_bars'].get('bar_diameter', 16)
            fig_beam = SectionVisualizer.draw_beam_section(b=gov["b_w"], h=gov["h_overall"], cover=beam_inputs.get("cover", cover), num_top=n_top, dia_top=d_top, num_bot=n_bot, dia_bot=d_bot)
            st.plotly_chart(fig_beam, use_container_width=True)
        st.markdown("---")
        st.subheader("Internal Force Diagrams (BMD & SFD)")
        st.caption("Plotted directly from the per-span end moments and shears used for design — not a generic textbook envelope.")
        fig_analysis = DiagramPlotter.plot_beam_diagrams(
            b_res["spans_detail"], default_w_ult=b_res.get("w_ult_kN_m")
        )
        st.plotly_chart(fig_analysis, use_container_width=True)

# ==========================================
# 4. COLUMN TAKEDOWN & DESIGN (RCC51)
# ==========================================
elif module == "Column Design":
    from elements.column import ColumnDesign
    from core.visualizer import SectionVisualizer
    st.subheader("Column Load Takedown & Design (Benchmarked against RCC51.xls)")

    beam_res_for_link = st.session_state.design_results.get("beam")
    use_beam_reactions = False
    if beam_res_for_link is not None:
        use_beam_reactions = st.checkbox(
            "🔗 Pull beam reactions from the Beam Design result",
            value=True,
            help=f"Beam Design gave Gk = {beam_res_for_link['reaction_gk_to_column_kN']} kN, "
                 f"Qk = {beam_res_for_link['reaction_qk_to_column_kN']} kN per beam reaction. "
                 "Uncheck to enter loads manually."
        )
    else:
        st.caption("Run **Beam Design** first to pull its reactions in automatically — otherwise enter loads manually below.")

    default_gk = beam_res_for_link["reaction_gk_to_column_kN"] if use_beam_reactions else 50.0
    default_qk = beam_res_for_link["reaction_qk_to_column_kN"] if use_beam_reactions else 25.0

    with st.form("column_inputs"):
        col1, col2, col3 = st.columns(3)
        with col1:
            col_b = st.number_input("Column Width, b (mm)", value=200.0, step=25.0)
        with col2:
            col_h = st.number_input("Column Depth, h (mm)", value=200.0, step=25.0)
        with col3:
            n_floors = st.number_input("Number of Storeys Supported", value=2, min_value=1, max_value=20, step=1)
        load1, load2 = st.columns(2)
        with load1:
            col_gk = st.number_input(
                "Beam Gk per Floor (kN)", min_value=0.0, value=float(default_gk), step=5.0,
                disabled=use_beam_reactions,
                help="Permanent beam reaction delivered to this column per supported floor."
            )
        with load2:
            col_qk = st.number_input(
                "Beam Qk per Floor (kN)", min_value=0.0, value=float(default_qk), step=5.0,
                disabled=use_beam_reactions,
                help="Variable beam reaction delivered to this column per supported floor."
            )
        if use_beam_reactions:
            st.caption("Gk/Qk above are locked to the Beam Design result. Uncheck the box above to override manually.")
        st.markdown("**Applied first-order moments (optional)**")
        st.caption(
            "This module does not run a full frame analysis. If you have design moments from unbalanced beam "
            "spans, wind, or another analysis, enter them here — otherwise only the code's minimum-eccentricity "
            "moment is checked (never zero, since that's never code-compliant for a real column)."
        )
        m1, m2 = st.columns(2)
        with m1:
            mx_applied = st.number_input("Applied Mx (kNm)", min_value=0.0, value=0.0, step=1.0, help="Design moment about the h (major) axis.")
        with m2:
            my_applied = st.number_input("Applied My (kNm)", min_value=0.0, value=0.0, step=1.0, help="Design moment about the b (minor) axis.")
        run_column = st.form_submit_button("Calculate Column", type="primary")
    show_column_visuals = st.checkbox("Show column section drawing", value=False)
    if run_column:
        gk_to_use = beam_res_for_link["reaction_gk_to_column_kN"] if use_beam_reactions else col_gk
        qk_to_use = beam_res_for_link["reaction_qk_to_column_kN"] if use_beam_reactions else col_qk
        if gk_to_use <= 0:
            st.error("Enter a positive beam Gk reaction per supported floor before running the column design.")
            st.stop()
        try:
            column = ColumnDesign(b=col_b, h=col_h, num_floors=n_floors, cover=cover, Gk_beam_per_floor=gk_to_use, Qk_beam_per_floor=qk_to_use, Mx_applied=mx_applied, My_applied=my_applied, f_cu=f_cu, f_y=f_y, code=code_choice)
            st.session_state.design_results["column"] = stamp_settings(column.design_column())
            st.session_state.design_inputs["column"] = dict(b=col_b, h=col_h, num_floors=n_floors, cover=cover, Gk_beam_per_floor=gk_to_use, Qk_beam_per_floor=qk_to_use, Mx_applied=mx_applied, My_applied=my_applied, f_cu=f_cu, f_y=f_y, code=code_choice)
            st.session_state.project_data["column_dims"] = {"b": col_b, "h": col_h}
        except ValueError as exc:
            st.error(f"Input error: {exc}")
    col_res = st.session_state.design_results.get("column")
    if col_res is None:
        st.info("Review the column inputs, then click **Calculate Column**.")
        st.stop()

    clear_result("column", "Clear Calculated Column Result")
    show_settings_drift_warning(col_res)
    col_data, col_plot = st.columns([1, 1])
    with col_data:
        axial_label = "NEd — Design Axial Force" if code_choice == "Eurocode 2" else "Nu — Ultimate Axial Load"
        st.metric(axial_label, f"{col_res['N_ult_total_kN']} kN")
        st.metric("Axial Resistance (NRd)", f"{col_res['N_rd_kN']} kN")
        st.metric("Required Steel Area (As,req)", f"{col_res['Asc_req_mm2']} mm²")
        show_utilization("Axial", col_res['N_ult_total_kN'], col_res['N_rd_kN'], "kN")
        if col_res["axial_resistance_status"] == "PASS":
            st.success(
                f"**Axial resistance: PASS** — NEd {col_res['N_ult_total_kN']} kN ≤ "
                f"NRd {col_res['N_rd_kN']} kN (utilization {col_res['axial_utilization']:.3f})"
            )
        else:
            st.error(
                f"**Axial resistance: FAIL** — NEd {col_res['N_ult_total_kN']} kN > "
                f"NRd {col_res['N_rd_kN']} kN"
            )
            st.caption("💡 Try increasing the column width/depth, or raising the concrete grade — both increase NRd directly.")
            if st.button("🔁 Retry with b/h +25mm each", key="retry_column_size"):
                saved_inputs = dict(st.session_state.design_inputs.get("column", {}))
                saved_inputs["b"] = saved_inputs.get("b", col_b) + 25.0
                saved_inputs["h"] = saved_inputs.get("h", col_h) + 25.0
                retry_column = ColumnDesign(**saved_inputs)
                st.session_state.design_results["column"] = stamp_settings(retry_column.design_column())
                st.session_state.project_data["column_dims"] = {"b": saved_inputs["b"], "h": saved_inputs["h"]}
                st.session_state.design_inputs["column"] = saved_inputs
                st.rerun()

        if not col_res["is_short"]:
            if code_choice == "Eurocode 2":
                st.warning(
                    f"⚠️ Slender column (EN 1992-1-1 5.8.3.1): λx = {col_res['slenderness_x']}, "
                    f"λy = {col_res['slenderness_y']} vs λlim = {col_res.get('lambda_lim')}. "
                    f"Nominal-curvature second-order moments M2x = {col_res.get('M2_x_kNm', 0)} kNm, "
                    f"M2y = {col_res.get('M2_y_kNm', 0)} kNm are included with φef = 2.0 — confirm the "
                    "creep ratio and end-moment assumptions for the project."
                )
            else:
                st.warning(
                    f"⚠️ Slender column: le/h = {col_res['slenderness_x']}, le/b = {col_res['slenderness_y']} "
                    "(> 15). The BS 8110 additional moment is included below."
                )

        st.markdown("##### Biaxial moment-axial interaction (simplified)")
        mcol1, mcol2, mcol3 = st.columns(3)
        mcol1.metric("Design Mx", f"{col_res['Mx_design_kNm']} kNm", help=f"Includes minimum eccentricity ({col_res['Mx_min_kNm']} kNm) and second-order moment (BS Madd {col_res['Madd_x_kNm']} / EC2 M2 {col_res.get('M2_x_kNm', 0)} kNm).")
        mcol2.metric("Design My", f"{col_res['My_design_kNm']} kNm", help=f"Includes minimum eccentricity ({col_res['My_min_kNm']} kNm) and second-order moment (BS Madd {col_res['Madd_y_kNm']} / EC2 M2 {col_res.get('M2_y_kNm', 0)} kNm).")
        if col_res["moment_utilization"] is not None:
            show_utilization("Moment interaction", col_res["moment_utilization"], 1.0, "")
        st.caption(
            f"Section capacities at the applied axial load: Mx,Rd = {col_res.get('Mx_Rd_kNm')} kNm, "
            f"My,Rd = {col_res.get('My_Rd_kNm')} kNm. Method: {col_res.get('moment_method', '—')}"
        )
        if col_res["moment_status"] == "PASS":
            st.success("**Moment interaction: PASS** (simplified linear approximation — see limitations).")
        else:
            st.error("**Moment interaction: FAIL** — increase section size, add reinforcement, or verify with a full column design chart.")

        st.success(f"**Longitudinal Main Bars:** {col_res['main_rebar']['description']}")
        st.write(f"**Confining Ties / Links:** `{col_res['link_schedule']}`")
        show_audit(col_res.get("audit", {}), "Column verification")
        download_calc_sheet("Column Design", col_res, "column")
        col_inputs = st.session_state.design_inputs.get("column", {})
        if col_inputs:
            from core.dxf_export import generate_column_dxf
            dxf_bytes = generate_column_dxf(
                col_res, b=col_inputs.get("b", col_b), h=col_inputs.get("h", col_h), cover=col_inputs.get("cover", cover),
                code=code_choice, project_name=st.session_state.get("project_name", ""), engineer_name=st.session_state.get("engineer_name", "")
            )
            download_dxf("Column Design", dxf_bytes, "column")
    if show_column_visuals:
        with col_plot:
            n_bars = col_res['main_rebar'].get('bars', 4)
            d_bar = col_res['main_rebar'].get('dia', 16)
            fig_col = SectionVisualizer.draw_column_section(b=col_b, h=col_h, cover=col_inputs.get("cover", cover), num_bars=n_bars, bar_dia=d_bar)
            st.plotly_chart(fig_col, use_container_width=True)

# ==========================================
# 5. PAD FOOTING (RCC81)
# ==========================================
elif module == "Pad Footing Design":
    from elements.footing import PadFooting
    from core.visualizer import SectionVisualizer
    st.subheader("Pad Footing Design (Benchmarked against RCC81.xls)")

    col_res_for_link = st.session_state.design_results.get("column")
    col_dims_for_link = st.session_state.project_data.get("column_dims")
    use_column_loads = False
    if col_res_for_link is not None:
        use_column_loads = st.checkbox(
            "🔗 Pull axial load from the Column Design result",
            value=True,
            help=f"Column Design gave N_service = {col_res_for_link['N_serv_to_footing_kN']} kN, "
                 f"N_ultimate = {col_res_for_link['N_ult_total_kN']} kN. Uncheck to enter loads manually."
        )
    else:
        st.caption("Run **Column Design** first to pull its axial load in automatically — otherwise enter loads manually below.")

    default_n_serv = col_res_for_link["N_serv_to_footing_kN"] if use_column_loads else 500.0
    default_n_ult = col_res_for_link["N_ult_total_kN"] if use_column_loads else 750.0
    default_col_cx = col_dims_for_link["b"] if col_dims_for_link else 200.0
    default_col_cy = col_dims_for_link["h"] if col_dims_for_link else 200.0

    with st.form("footing_inputs"):
        qa = st.number_input("Safe Soil Bearing Capacity (kN/m²)", value=150.0, step=10.0)
        pad_default_m = float(st.session_state.project_data["pad_dim"]) / 1000.0
        col1, col2, col3 = st.columns(3)
        with col1:
            N_serv = st.number_input("Service Axial Load (kN)", value=float(default_n_serv), min_value=0.0, step=25.0, disabled=use_column_loads)
        with col2:
            N_u = st.number_input("Ultimate Axial Load (kN)", value=float(default_n_ult), min_value=0.0, step=50.0, disabled=use_column_loads)
        with col3:
            pad_detected = bool(
                st.session_state.project_data.get("has_drawing")
                and st.session_state.project_data.get("pad_dim_detected")
            )
            if pad_detected:
                override = st.checkbox("Use Auto-Imported Footing Dimensions from Drawing", value=True)
            else:
                override = False
                st.caption("No pad size was detected in the uploaded drawing — the footing will be auto-sized from the load and soil capacity.")
        cc1, cc2 = st.columns(2)
        with cc1:
            col_cx_in = st.number_input("Column Width, cx (mm)", value=float(default_col_cx), step=25.0)
        with cc2:
            col_cy_in = st.number_input("Column Depth, cy (mm)", value=float(default_col_cy), step=25.0)
        h_overall_in = st.number_input("Footing Overall Depth, h (mm)", value=450.0, min_value=200.0, step=25.0, help="Total footing thickness including cover — adjust if the default doesn't suit your soil/load conditions.")
        if use_column_loads:
            st.caption("Axial loads above are locked to the Column Design result. Uncheck the box above to override manually.")
        run_footing = st.form_submit_button("Calculate Footing", type="primary")
    show_footing_visuals = st.checkbox("Show footing section drawing", value=False)
    if run_footing:
        n_serv_to_use = col_res_for_link["N_serv_to_footing_kN"] if use_column_loads else N_serv
        n_u_to_use = col_res_for_link["N_ult_total_kN"] if use_column_loads else N_u
        if n_u_to_use < n_serv_to_use:
            st.error("Ultimate axial load should not be less than service axial load.")
            st.stop()
        try:
            footing = PadFooting(N_service=n_serv_to_use, N_ultimate=n_u_to_use, col_cx=col_cx_in, col_cy=col_cy_in, q_allowable=qa, h_overall=h_overall_in, cover=cover, f_cu=f_cu, f_y=f_y, code=code_choice)
        except ValueError as exc:
            st.error(f"Input error: {exc}")
            st.stop()
        use_imported = bool(override and pad_detected)
        if use_imported:
            pad_L, pad_B = pad_default_m, pad_default_m
        else:
            pad_L, pad_B, _ = footing.size_plan_dimensions()
        footing_result = stamp_settings(footing.design_reinforcement_and_shear(pad_L, pad_B))
        st.session_state.design_results["footing"] = stamp_settings({
            "result": footing_result, "pad_L": pad_L, "pad_B": pad_B,
            "used_imported_dimensions": use_imported,
        })
        st.session_state.design_inputs["footing"] = dict(N_service=n_serv_to_use, N_ultimate=n_u_to_use, col_cx=col_cx_in, col_cy=col_cy_in, q_allowable=qa, h_overall=h_overall_in, cover=cover, f_cu=f_cu, f_y=f_y, code=code_choice)
    saved_footing = st.session_state.design_results.get("footing")
    if saved_footing is None:
        st.info("Review the footing inputs, then click **Calculate Footing**.")
        st.stop()
    clear_result("footing", "Clear Calculated Footing Result")
    f_res = saved_footing["result"]
    show_settings_drift_warning(saved_footing)
    pad_L, pad_B = saved_footing["pad_L"], saved_footing["pad_B"]

    if saved_footing.get("used_imported_dimensions", False):
        st.info(f"Using Footing Base: **{pad_L:.2f}m × {pad_B:.2f}m** extracted from drawing schedule.")

    col_data, col_plot = st.columns([1, 1])
    with col_data:
        st.metric("Footing Size", f"{pad_L:.2f} × {pad_B:.2f} m")
        st.metric("Service Bearing Pressure", f"{f_res['q_service_kpa']} kN/m²")
        st.metric("Design Moment (Mu)", f"{f_res['M_u_kNm_per_m']} kNm/m")
        st.metric("Required As", f"{f_res['As_req_mm2_m']} mm²/m")
        show_utilization("Bearing pressure", f_res['q_service_kpa'], qa, "kN/m²")
        if f_res['q_service_kpa'] > qa:
            st.caption(f"💡 Bearing pressure exceeds allowable — increase the plan size beyond {pad_L:.2f}×{pad_B:.2f}m, or confirm the soil bearing capacity with a geotechnical report.")
            if st.button("🔁 Retry with plan size +200mm each way", key="retry_footing_size"):
                saved_inputs = dict(st.session_state.design_inputs.get("footing", {}))
                retry_footing = PadFooting(**saved_inputs)
                new_L, new_B = pad_L + 0.2, pad_B + 0.2
                new_result = retry_footing.design_reinforcement_and_shear(new_L, new_B)
                st.session_state.design_results["footing"] = stamp_settings({
                    "result": new_result, "pad_L": new_L, "pad_B": new_B, "used_imported_dimensions": False
                })
                st.rerun()
        st.success(f"**Reinforcement Mat:** {f_res['rebar']['description']}")
        st.write(f"**One-way shear stress:** {f_res['v_1way_Nmm2']} N/mm²")
        st.write(f"**Punching shear stress:** {f_res['v_punch_Nmm2']} N/mm²")
        show_audit(f_res.get("audit", {}), "Footing verification")
        download_calc_sheet("Pad Footing Design", f_res, "footing")
        footing_inputs = st.session_state.design_inputs.get("footing", {})
        if footing_inputs:
            from core.dxf_export import generate_footing_dxf
            dxf_bytes = generate_footing_dxf(
                f_res, pad_L, pad_B, col_cx=footing_inputs.get("col_cx", 200), col_cy=footing_inputs.get("col_cy", 200),
                code=code_choice, project_name=st.session_state.get("project_name", ""), engineer_name=st.session_state.get("engineer_name", "")
            )
            download_dxf("Pad Footing Design", dxf_bytes, "footing")
    if show_footing_visuals:
        with col_plot:
            fig_foot = SectionVisualizer.draw_footing_elevation(
                pad_L_m=pad_L, pad_h_mm=f_res.get("h_overall_mm", 450.0),
                col_dim_mm=footing_inputs.get("col_cx", 200.0),
                cover_mm=f_res.get("cover_mm", 50.0),
            )
            st.plotly_chart(fig_foot, use_container_width=True)

# ==========================================
# 6. TWO-WAY SLAB & STAIRS
# ==========================================
elif module == "Slab Design":
    from elements.slab import TwoWaySlab, OneWaySlab
    st.subheader("Slab Design")
    slab_mode = st.radio("Slab type", ["Two-way slab", "One-way slab"], horizontal=True, help="Choose whether the slab acts primarily in one direction or in two directions. The one-way model is a preliminary simply-supported 1 m strip analysis.")
    with st.form("slab_inputs"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            lx = st.number_input("Short Span, lx (m)", value=float(st.session_state.project_data["span_x"]), step=0.25, min_value=0.0)
        with col2:
            ly = st.number_input("Long Span, ly (m)", value=float(st.session_state.project_data["span_y"]), step=0.25, min_value=0.0)
        with col3:
            h_slab = st.number_input("Slab Thickness, h (mm)", value=float(st.session_state.project_data["slab_thick"]), step=10.0, min_value=0.0)
        with col4:
            if slab_mode == "Two-way slab":
                panel_type = st.selectbox("Edge / Panel Condition", list(TwoWaySlab.BS_COEFFS), help="BS 8110-1:1997 Table 3.14 panel classifications.")
            else:
                panel_type = "Simply Supported"
        sl1, sl2 = st.columns(2)
        with sl1:
            slab_gk = st.number_input("Finishes / Partitions Gk (kN/m²)", value=1.5, min_value=0.0, step=0.25)
        with sl2:
            slab_qk = st.number_input("Imposed Qk (kN/m²)", value=2.0, min_value=0.0, step=0.5)
        run_slab = st.form_submit_button("Calculate Slab", type="primary")
    if run_slab:
        try:
            if slab_mode == "Two-way slab":
                slab = TwoWaySlab(lx=lx, ly=ly, h_slab=h_slab, cover=cover, gk_finishes=slab_gk, qk_live=slab_qk, f_cu=f_cu, f_y=f_y, panel_type=panel_type, code=code_choice)
                result = slab.design_panel()
            else:
                if lx <= 0:
                    raise ValueError("One-way slab span must be greater than 0 m.")
                slab = OneWaySlab(span=lx, h_slab=h_slab, cover=cover, gk_finishes=slab_gk, qk_live=slab_qk, f_cu=f_cu, f_y=f_y, code=code_choice)
                result = slab.design()
            st.session_state.design_results["slab"] = stamp_settings({"result": result, "panel_type": panel_type, "mode": slab_mode})
        except ValueError as exc:
            st.error(f"Input error: {exc}")
    saved_slab = st.session_state.design_results.get("slab")
    if saved_slab is None:
        st.info("Review the slab inputs, then click **Calculate Slab**.")
        st.stop()
    clear_result("slab", "Clear Calculated Slab Result")
    res = saved_slab["result"]
    show_settings_drift_warning(saved_slab)
    panel_type = saved_slab["panel_type"]
    mode = saved_slab.get("mode", "Two-way slab")
    st.metric("Ultimate Design Load", f"{res['n_ult_kpa']} kN/m²")
    st.caption(f"Analysis: {res['analysis_method']} — {panel_type}")
    st.markdown("### Load breakdown")
    if mode == "Two-way slab":
        st.write(f"Self-weight: **{res['gk_self_kpa']:.2f} kN/m²**  ·  Finishes/partitions: **{res['gk_finishes_kpa']:.2f} kN/m²**  ·  Total Gk: **{res['gk_slab_kpa']:.2f} kN/m²**  ·  Qk: **{res['qk_slab_kpa']:.2f} kN/m²**")
        st.markdown("### Design moments")
        mc1, mc2 = st.columns(2)
        mc1.metric("Positive Mx", f"{res['Msx_pos']} kNm/m")
        mc2.metric("Positive My", f"{res['Msy_pos']} kNm/m")
        mc3, mc4 = st.columns(2)
        mc3.metric("Negative Mx", f"{res['Msx_neg']} kNm/m")
        mc4.metric("Negative My", f"{res['Msy_neg']} kNm/m")
        st.markdown("### Reinforcement")
        st.success(f"**Bottom X:** {res['rebar_sx']['description']} — required {res['rebar_sx']['As_req']} mm²/m; provided {res['rebar_sx']['As_prov']} mm²/m")
        st.success(f"**Bottom Y:** {res['rebar_sy']['description']} — required {res['rebar_sy']['As_req']} mm²/m; provided {res['rebar_sy']['As_prov']} mm²/m")
        if res['rebar_sx_neg']['As_req'] > 0 or res['rebar_sy_neg']['As_req'] > 0:
            st.info(f"**Top X:** {res['rebar_sx_neg']['description']} — required {res['rebar_sx_neg']['As_req']} mm²/m; **Top Y:** {res['rebar_sy_neg']['description']} — required {res['rebar_sy_neg']['As_req']} mm²/m")
        else:
            st.info("**Top reinforcement:** No negative support moment is generated by the selected panel condition.")
        st.write(
            f"**Crack width (quasi-permanent):** {res.get('crack_status', 'NOT CHECKED')} — "
            f"bottom X {res.get('wk_x_pos_mm', '—')} mm, bottom Y {res.get('wk_y_pos_mm', '—')} mm, "
            f"top X {res.get('wk_x_neg_mm', '—')} mm, top Y {res.get('wk_y_neg_mm', '—')} mm"
        )
        if res.get("deflection_status") in ("PASS", "FAIL"):
            span_d_msg = f"span/d = {res['actual_span_d']} vs allowable {res['allowable_span_d']}"
            if res["deflection_status"] == "PASS":
                st.success(f"**Deflection screening: PASS** — {span_d_msg}")
            else:
                st.error(f"**Deflection screening: FAIL** — {span_d_msg} (increase thickness or reduce span)")
        show_audit(res.get("audit", {}), "Slab verification")
        download_calc_sheet("Two-Way Slab Design", res, "slab")
    else:
        st.write(f"Self-weight: **{res['gk_self_kpa']:.2f} kN/m²**  ·  Finishes/partitions: **{res['gk_finishes_kpa']:.2f} kN/m²**  ·  Total Gk: **{res['gk_total_kpa']:.2f} kN/m²**  ·  Qk: **{res['qk_kpa']:.2f} kN/m²**")
        mc1, mc2 = st.columns(2)
        mc1.metric("Design Moment Mu", f"{res['M_u_kNm_per_m']} kNm/m")
        mc2.metric("Design Shear Vu", f"{res['V_u_kN_per_m']} kN/m")
        st.success(f"**Main reinforcement:** {res['rebar']['description']} — required {res['As_req_mm2_m']} mm²/m; provided {res['rebar']['As_prov']} mm²/m")
        st.write(f"**Shear stress:** {res.get('v_stress_Nmm2', 'n/a')} N/mm²")
        st.write(f"**Crack width (quasi-permanent):** {res.get('crack_status', 'NOT CHECKED')} — wk = {res.get('wk_mm', '—')} mm")
        if res.get("deflection_status") in ("PASS", "FAIL"):
            span_d_msg = f"span/d = {res['actual_span_d']} vs allowable {res['allowable_span_d']}"
            if res["deflection_status"] == "PASS":
                st.success(f"**Deflection screening: PASS** — {span_d_msg}")
            else:
                st.error(f"**Deflection screening: FAIL** — {span_d_msg} (increase thickness or reduce span)")
        show_audit(res.get("audit", {}), "Slab verification")
        st.caption("Preliminary one-way model: simply supported 1 m strip. Support continuity and full serviceability checks are not modelled.")
        download_calc_sheet("One-Way Slab Design", res, "slab")


elif module == "Stair Design":
    from elements.stair import StairFlight
    st.subheader("Stair Flight & Landing Design (Benchmarked against RCC71.xls)")
    with st.form("stair_inputs"):
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            going = st.number_input("Tread Going (mm)", value=250.0, step=10.0)
        with sc2:
            rise = st.number_input("Step Rise (mm)", value=150.0, step=10.0)
        with sc3:
            waist = st.number_input("Waist Thickness (mm)", value=175.0, step=10.0)
        with sc4:
            flight_len = st.number_input("Flight Going Length (m)", value=2.4, step=0.25,
                                         help="Horizontal length of the stepped flight, excluding the landing.")
        st1, st2, st3 = st.columns(3)
        with st1:
            landing_len = st.number_input("Landing Span (m)", value=1.2, min_value=0.1, step=0.1)
        with st2:
            stair_gk = st.number_input("Finishes Gk (kN/m²)", value=1.2, min_value=0.0, step=0.25)
        with st3:
            stair_qk = st.number_input("Imposed Qk (kN/m²)", value=3.0, min_value=0.0, step=0.5)
        run_stair = st.form_submit_button("Calculate Stair", type="primary")
    if run_stair:
        stair = StairFlight(going=going, rise=rise, waist=waist, flight_going_len=flight_len, landing_len=landing_len, cover=cover, gk_finishes=stair_gk, qk_live=stair_qk, f_cu=f_cu, f_y=f_y, code=code_choice)
        st.session_state.design_results["stair"] = stamp_settings(stair.design_stair())
    s_res = st.session_state.design_results.get("stair")
    if s_res is None:
        st.info("Review the stair inputs, then click **Calculate Stair**.")
        st.stop()
    clear_result("stair", "Clear Calculated Stair Result")
    show_settings_drift_warning(s_res)
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Design Moment (Mu)", f"{s_res['M_u_kNm']} kNm/m")
    sc2.metric("Design Shear (Vu)", f"{s_res.get('V_u_kN_m', '—')} kN/m")
    sc3.metric("Effective Span", f"{s_res['L_eff_m']} m")
    st.success(f"**Main Tension Rebar:** {s_res['main_rebar']['description']}")
    st.info(f"**Distribution Steel:** {s_res['dist_rebar']['description']}")
    if s_res.get("shear_status") == "PASS":
        st.success(
            f"**Shear: PASS** — v = {s_res['v_stress_Nmm2']} N/mm² ≤ "
            f"{s_res['v_capacity_Nmm2']} N/mm²"
        )
    else:
        st.error(
            f"**Shear: FAIL** — v = {s_res.get('v_stress_Nmm2')} N/mm² > "
            f"{s_res.get('v_capacity_Nmm2')} N/mm² (increase the waist)"
        )
    if s_res.get("deflection_status") in ("PASS", "FAIL"):
        if s_res["deflection_status"] == "PASS":
            st.success(f"**Deflection screening: PASS** — L/d = {s_res['actual_span_d']} ≤ {s_res['allowable_span_d']}")
        else:
            st.error(f"**Deflection screening: FAIL** — L/d = {s_res['actual_span_d']} > {s_res['allowable_span_d']} (increase waist)")
    st.write(f"**Crack width (quasi-permanent):** {s_res.get('crack_status', 'NOT CHECKED')} — wk = {s_res.get('wk_mm', '—')} mm")
    show_audit(s_res.get("audit", {}), "Stair verification")
    st.caption(f"End reaction to landing/floor beam: {s_res.get('reaction_to_beam_kN_m')} kN/m.")
    download_calc_sheet("Stair Design", s_res, "stair")