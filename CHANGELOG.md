# Changelog

## v24 — Fix 3D chart scroll-trap; improve help search recall

**3D preview scroll trap fixed properly.** Plotly 3D (WebGL) canvases can
capture and block the mouse-wheel scroll event even with `scrollZoom: False`
set — a known browser/Plotly interaction issue, not something fixable by
chart configuration alone. The 3D preview in Whole Building Design is now
opened via an explicit button into a modal dialog (`st.dialog`) with a
visible **Close** button, rather than sitting inline in the page's normal
scroll flow. There is no longer any state where the page can get "stuck" —
if the dialog isn't open, the 3D canvas doesn't exist on the page at all.

**Help search recall improved.** The keyword-overlap scoring previously
divided by the *query's* word count, so a long, casually-phrased question
("what's the deal with this NOT CHECKED thing") got diluted by its own
filler words and scored lower than a short, precise one — even though it
contained the exact right terms. Switched to recall-based scoring
(overlap ÷ number of keywords in the entry) so wordy, casual phrasing is no
longer penalised. Threshold re-tuned against real matching/non-matching
examples after the scoring change (0.35, sitting between the highest
genuine non-match at 0.33 and the lowest genuine match at 0.37).

Two new FAQ entries added (general app troubleshooting, "a result looks
wrong") — these are deliberately NOT auto-triggered by vague phrasing like
"my app crashed," since testing showed that pushes the match threshold low
enough to also let genuinely unrelated queries through. They remain fully
visible in the "Browse all topics" list instead — an honest trade-off of a
keyword-based search rather than a true NLU model.

2 new tests (38 total) locking in the casual-phrasing fix and confirming
genuinely unrelated queries still correctly return no match.

## v23 — Built-in help search (no AI, no external service)

**New: `core/help_assistant.py`** — a lightweight, dependency-free help
search using only Python's standard library (`difflib`), explicitly NOT a
machine learning model or LLM:

- A curated FAQ covering PASS/FAIL/WARNING/NOT CHECKED, the 🔗 linking
  checkboxes, retry buttons, settings-drift warnings, the drawing importer's
  "not detected" behavior, DXF troubleshooting, save/load, and what the
  simplified column moment check means.
- Also searches the engineer's **own current session results** — every
  audit message and limitation already produced by the calc engine for
  whatever they've calculated — so a question about a specific result
  surfaces the exact text the engine wrote, never an invented answer.
- A relevance threshold (tuned against real query/non-query examples, not
  guessed) so an unrelated question returns "no match" honestly instead of
  a confident-looking wrong guess.

**Hard scope boundary, by design**: this never generates a new engineering
opinion. Every answer either quotes the tool's own documentation or a
message the calc engine already produced — it cannot judge whether a
design is adequate beyond what's already been checked.

**UI**: a new "Help & Troubleshooting" sidebar module with search + browsable
FAQ + session-specific results; plus a "❓ Ask about this result" box
directly under every audit table, right where the question naturally comes
up.

6 new tests (36 total) covering FAQ retrieval accuracy, the irrelevant-query
rejection threshold, and that dynamic session-result entries surface real
audit text rather than anything invented.

## v22 — Real CAD-quality reinforcement detail drawings (DXF export)

**New: `core/dxf_export.py`** generates dimensioned, layered DXF drawings from
the calculated reinforcement — openable in AutoCAD, BricsCAD, LibreCAD, or any
DXF-capable viewer, not just a schematic preview inside the app:

- **Beam**: mid-span and support cross-sections side by side, with bottom/top
  bar counts and diameters, link callout, and section dimensions.
- **Column**: cross-section with main bar layout (4/6/8/10-bar symmetric
  arrangements), tie/link callout, and section dimensions.
- **Footing**: reinforcement mat plan view (both-way bar grid at true
  spacing), dashed column outline, and plan dimensions.

Every drawing has a title block with project name, engineer, code, date, key
design results, and an explicit "PRELIMINARY DESIGN AID — NOT FOR
CONSTRUCTION" notice — the same honesty posture as the calc sheets, applied
to the drawings this time, since diagrams need to be trusted too, not just
numbers.

"📐 Download reinforcement detail (DXF)" buttons added to Beam, Column and
Pad Footing modules, alongside the existing calc-sheet download. The DXF
always reflects whichever inputs actually produced the current result
(including after a "retry with +Xmm" button), not stale form values.

1 new test (30 total) verifying all three DXF exports round-trip through
`ezdxf.read()` without error. Drawings were also visually verified by
rendering to PNG during development — see the geometry checks in this
session — to confirm bar layout, dimensions and leader lines render cleanly
(an earlier draft had crossing leader lines and overlapping title-block
text; both were caught and fixed before shipping).

## v21 — Column biaxial bending and slenderness (simplified)

**Column Design is no longer axial-only.** This closes the biggest single gap
identified for real-world use (a genuine column almost always carries some
moment, not pure axial load):

- **Minimum eccentricity moment** (BS 8110 Cl. 3.8.2.4 / EC2 Cl. 6.1(4)) is now
  always checked, even with zero applied moment — the code never actually
  permits pure axial design.
- **Optional applied first-order moments (Mx, My)** — an engineer can enter
  design moments from a frame analysis, unbalanced beam spans, or wind; the
  module does not derive these itself (no full frame analysis is implemented).
- **Slenderness / second-order moment** — BS 8110 braced slender columns
  (Cl. 3.8.3.1, simplified K=1) get an additional moment automatically added.
  EC2 second-order effects are explicitly NOT CHECKED rather than silently
  ignored, since the nominal curvature method isn't implemented.
- **Biaxial-to-uniaxial reduction** — BS 8110's Table 3.24 beta-factor method
  (Cl. 3.8.4.5) for BS8110, EC2's exponent method (Cl. 5.8.9(4)) for Eurocode 2.
- **Capacity check** uses a simplified straight-line (linear) N-M interaction
  between the pure-axial and an approximate pure-moment capacity. This is
  explicitly labelled as conservative and NOT a full strain-compatibility
  interaction diagram — a close-to-1.0 or FAIL result means "check with a
  full column design chart," not "this column has failed."
- Fixed a false-FAIL bug caught during testing: BS 8110's axial resistance
  formula (0.4fcu·Ac + 0.75fy·Asc) already has minimum eccentricity built in
  per Cl. 3.8.4.3, so a plain short column with no real applied moment
  correctly shows PASS rather than being double-penalised by the new
  interaction check.
- New Column Design UI: optional Mx/My input fields, slenderness warning
  banner, and a moment-interaction utilization display alongside the
  existing axial check.
- 3 new tests (29 total, all passing) covering the false-FAIL fix and both a
  failing and a passing slender-column-with-moment case.

## v20 — Retry-on-fail, save/load projects, settings-drift warnings

- **Retry-on-fail buttons**: when Beam deflection, Column axial resistance, or Footing
  bearing pressure comes back FAIL, a one-click "🔁 Retry with ..." button reruns the
  calculation with the suggested change (e.g. depth +50mm, column +25mm each way,
  footing plan +200mm each way) instead of the engineer manually reopening the form.
- **Save / load project**: sidebar section to download the whole session (global
  settings, project name/engineer, imported drawing values, every calculated element
  and its inputs) as a `.json` file, and reload it later to resume exactly where you
  left off. Drawing page images are intentionally excluded from the save file to keep
  it small; re-upload the drawing if needed after reloading.
- **Settings-drift warning**: every calculated element now records the code/fcu/fy it
  was calculated with. If the sidebar's global settings are changed afterwards, the
  affected module shows an explicit warning that its results no longer match the
  current settings and should be recalculated — instead of silently going stale.

## v19 — Load path continuity, Project Dashboard, and clearer feedback

**Modules now talk to each other instead of requiring manual re-entry:**
- Column Design can pull its Gk/Qk beam reaction straight from the last Beam Design
  result (🔗 checkbox, on by default when a beam result exists) instead of the
  engineer re-typing numbers already computed.
- Pad Footing Design can likewise pull its service/ultimate axial load from the last
  Column Design result, and now also inherits the column's plan dimensions instead of
  a hardcoded 200×200mm assumption.
- Both links are opt-out, not forced — unchecking the box always allows manual entry.

**New: Project Dashboard** (now the default landing module). One glance shows, for every
element calculated so far: pass/fail/not-checked counts, an overall project status
banner, a load-path continuity summary (beam reaction → column axial → footing size),
and a button to generate one combined calc sheet across every calculated element.

**Clearer, more actionable feedback:**
- Utilization bars (`show_utilization`) added to column axial resistance, beam/slab
  shear where applicable, and footing bearing pressure — so an engineer sees "how
  close", not just PASS/FAIL.
- FAIL messages now include a one-line suggestion of what to change (increase depth,
  increase footing size, raise concrete grade, etc.) instead of leaving the engineer
  to guess the next iteration.

## v18 — Close NOT CHECKED gaps, honest ingestion, per-module calc sheets

**Engineering checks previously marked NOT CHECKED are now real PASS/FAIL:**
- BS 8110 footing punching shear (screening check at the 1.5d critical perimeter).
- EC2 beam shear design (variable strut inclination method, EN 1992-1-1 6.2), including link spacing output.
- Deflection span/effective-depth screening for beams, one-way slabs and two-way slabs
  (BS 8110 3.4.6 basic-ratio method — the same approach already used for stairs).
- One-way slab shear (unreinforced-slab concrete shear stress screening, both codes).
- EC2 deflection screening is intentionally still NOT CHECKED — no unreferenced formula was
  invented for it.

**Ingestion no longer fabricates values:**
- `pipeline/pdf_reader.py` and `pipeline/dxf_reader.py` return `None` + a `*_detected` flag
  instead of silently defaulting to plausible-looking numbers (e.g. `[4.0, 5.0]` m,
  `150mm`, `1350mm`) when nothing is found in the drawing.
- `pipeline/dxf_reader.py` now reads the DXF `$INSUNITS` header for unit detection and only
  falls back to the old length-based heuristic when the header doesn't declare units,
  flagging that fallback explicitly.
- The CAD/PDF importer UI shows "✅ Detected" vs "⚠️ Not detected — enter manually" per field
  and requires the engineer to confirm every value in a form before it syncs to any design
  module.

**New: per-module calc sheet export.** Beam, Column, Footing, Slab and Stair modules each
get a "Download calc sheet (HTML)" button producing a standalone, printable report with
project/engineer name, all inputs, and the full verification audit — not just the
whole-building workflow.

## v16 — Slab workflow, UI cleanup, documentation and 3D placement

### User interface
- Removed decorative emojis from the application interface.
- Renamed the navigation item **Two-Way Slab (Panel 1)** to **Slab Design**.
- Renamed the slab selector to **Slab type** and presents One-way slab / Two-way slab choices inside the module.
- Kept engineering terminology inside the relevant design workflow instead of forcing technical implementation names into navigation.

### 3D workflow
- Moved the interactive 3D structural preview to the bottom of the Whole Building workflow.
- Kept Plotly wheel zoom disabled so the embedded model does not intentionally use the mouse wheel for zooming.
- Clarified that the model is a structural schematic and that the automated gravity calculation remains a representative internal-bay calculation.

### Documentation
- Added USER_GUIDE.md covering setup, modules, slab types, NEd/Nu terminology, verification statuses, load path, 3D behaviour and engineering review responsibilities.

### Engineering transparency
- Preserved PASS / FAIL / NOT CHECKED / WARNING / N/A verification states.
- Preserved the deliberate distinction between Eurocode 2 NEd and BS 8110 Nu.
- No unsupported slab types were exposed as completed design methods. Future slab systems remain roadmap items until their appropriate calculations and checks are implemented.

### Lightweight design
- No new runtime dependencies added.

## v17
- Renamed engineering navigation to user-facing names: Beam Design, Column Design, Pad Footing Design, Slab Design, Stair Design.
- Moved parametric section drawings before the optional 3D viewer; 3D is now the final visual block in Whole Building.
- Reworked reinforcement quantity/cost estimate with explicit BBS weight, editable procurement allowance, procurement quantity, diameter breakdown and cost.
- Corrected nominal reinforcing-bar mass calculation to d²/162 kg/m.
