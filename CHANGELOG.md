# Changelog

## v28 — Real multi-span beam analysis: unequal lengths, independent depths, uncapped span count

Direct response to engineer feedback: the beam module previously **rejected**
unequal spans outright, used one single depth/width for the entire beam,
and the UI hard-capped span count at 3 via a `[1, 2, 3]` dropdown. This was
the single biggest reason the tool felt less capable than the Excel sheets
it's meant to replace.

**New engine (`core/beam_analysis.py`, built on a solver that already
existed in the repo from earlier exploratory work but was never wired into
the actual beam module):** a real matrix (slope-deflection) structural
analysis, not a coefficient lookup table. Verified against independently-
checkable textbook results before anything was built on top of it — single
span reduces exactly to wL²/8, two equal spans to the classic wL²/8 support
moment and 9wL²/128 span moment, three equal spans to the classic wL²/10
interior support moment, and unequal-span cases satisfy moment equilibrium
at every shared support.

**Added: BS 8110/EC2-style pattern loading.** Loading every span
simultaneously understates the true maximum span moment under live load —
verified directly: the same beam's governing span moment came out ~15%
higher under proper alternate-span pattern loading than under a naive
"load everything at once" analysis. This is now run as the standard set of
load cases (all-loaded, alternating, adjacent-pair) with the worst case
taken as the design envelope, so nothing is silently unconservative.

**`ContinuousBeam` now accepts independent length, width, AND depth per
span** (pass a list for any of these, or a single number to apply
uniformly). Span count is no longer capped — tested up to 6+ spans.

**New Beam Design UI**: an editable per-span table (`st.data_editor`) —
add or remove spans freely, set each one's own length/width/depth/loads,
much closer to the spreadsheet-like editing freedom engineers actually
want. Results show a full per-span breakdown table (moments, reinforcement,
shear, deflection status for every span) alongside the existing governing-
span summary that the DXF export and calc sheet already depend on.

**Verified with real runtime testing, not just unit tests**: used
Streamlit's `AppTest` framework to actually navigate to Beam Design, click
Calculate with real per-span data, and confirm the full pipeline — results
display, per-span table, audit, DXF download — runs with zero exceptions.
Also fixed an unrelated pre-existing bug found along the way: the beam
section visualizer was reading `.get('bars')`/`.get('dia')` when the real
keys are `bar_count`/`bar_diameter`, so it was always silently drawing a
placeholder 2Y16 regardless of what was actually selected.

9 new/updated tests (51 total): 2 new tests in `test_beam_analysis.py`
covering pattern loading specifically (including a safety-critical
regression test that the envelope must never be lower than the naive
all-loaded case), and 3 new tests in `test_elements.py` covering genuinely
unequal spans, independent per-span width/depth, and uncapped span count.

**Explicitly deferred, clearly scoped for next steps** (this session
focused on doing the span/length/depth engineering correctly rather than
spreading across everything at once):
- Cantilever/fixed-end support conditions — both beam ends are still
  assumed simply supported.
- T-beam / L-beam (flanged section) design — only rectangular sections
  are supported.
- Point loads — only uniformly distributed load is modelled.
- Manual reinforcement/spacing override with live re-validation (the
  "Excel-style freedom with guardrails" feature discussed alongside the
  RCC94 comparison).

## v27 — Fix deflection basic-ratio bug (found via real RCC94 comparison), add first real benchmark test

A user ran the same panel through both this tool and an actual RCC94.xls
spreadsheet (BS 8110 Table 3.14 two-way slab) and compared the outputs
directly. Every design moment matched the reference to within rounding —
a genuine validation of the coefficient-method implementation — but the
comparison also surfaced a real bug:

**Fixed: deflection screening basic-ratio classification was wrong for
most panel types.** The two-way slab deflection check only used BS 8110's
"continuous" basic ratio (26) when the panel type was literally the string
"Interior Panel", defaulting to "simply supported" (20) for every other
panel type — including panels that are genuinely continuous on part of
their short span, like "Two Adjacent Edges Discontinuous". This made the
screening check unnecessarily conservative (in the reference case, 34.51
instead of the correct ~39-41 range) and could produce a false FAIL on a
marginal slab where the real BS 8110 method would pass. Replaced with a
proper classification based on which specific edges BS 8110 Table 3.14
treats as discontinuous for each of the 9 panel types — only the 3 panel
types where BOTH short-span edges are discontinuous now use the
simply-supported ratio; the other 6 correctly use the continuous ratio.
Verified against the real RCC94 output: allowable span/d moved from 34.51
(12% too conservative) to 40.9 (within ~4% of the reference's 39.21, an
appropriate level of agreement for a documented "simplified screening"
check, not a full deflection calculation).

**New: `tests/test_rcc94_benchmark.py`** — the first real benchmark test
using an actual spreadsheet's output as the expected values, not a
synthetic hand-calculation. This is the RCC41/51/81/71-style benchmarking
approach that was on the deferred backlog; this is the first concrete
instance of it, covering the two-way slab moment coefficients and the
deflection basic-ratio fix specifically, so this exact bug can never
silently reappear.

Also corrected an earlier (incorrect) hypothesis from reviewing the same
comparison: the two-way slab's four flexural checks (Bottom X/Y, Top X/Y)
showing identical demand/capacity in that example is NOT a missing
per-zone optimization bug — the engine does check each zone
independently; they coincidentally all landed on the same governing
minimum-steel value in that specific case. Confirmed by reading the
actual code before concluding anything, not assumed.

2 new tests (42 total).

## v26 — Consolidated engineering-usability batch (from GitLab audit + own review)

Following an independent audit (via a trial of GitLab's AI review tools) that
correctly identified several real gaps, this batch fixes what was verified
against the actual code — not everything suggested, and every claim was
checked before acting on it.

**Bug fixes:**
- "Clear Clear Calculated..." duplicate text in all 6 modules.
- Two-way slab load breakdown previously hardcoded finishes display at
  1.50 kN/m² and subtracted that same hardcoded number from the total,
  regardless of what the engineer actually entered. Fixed at the source:
  `TwoWaySlab` now returns real `gk_self_kpa`/`gk_finishes_kpa` fields
  (mirroring what `OneWaySlab` already did correctly), and the display
  uses them.
- Pad footing schematic drawing used a hardcoded 300mm depth that didn't
  even match the actual (also-hardcoded) 450mm calculation default.

**Real engineering-accuracy fix:** every Eurocode 2 calculation was silently
converting the sidebar's concrete strength input via `fck = 0.8 × fcu`,
treating the input as a BS8110-style cube strength. This is only a rough
approximation — EC2 concrete classes are defined by cylinder strength
directly. The sidebar now asks for the correct value per code (real EC2
fck classes: 16–50 MPa, BS8110 fcu classes now extended to include 40, 45,
50) and the 0.8 conversion was removed from all 7 places it appeared
(beam, column, footing ×2, slab ×3, stair). One existing test's expected
value was updated to reflect the corrected (not approximated) behavior.

**New: cover and exposure condition as a global project setting.** Cover
was previously hardcoded at 25mm everywhere with no way to change it —
a genuine gap for a real tool, since cover depends on exposure condition
and getting it wrong is a durability issue. The sidebar now has an
exposure-condition dropdown (Mild/Moderate/Severe/Very Severe/Extreme)
with a suggested cover, editable directly. Wired through to Beam, Column,
Footing, Slab, and Stair construction, and their section visuals/DXF
exports.

**New: Footing overall depth is now a real input** (previously always a
silent 450mm default with no UI control).

**Simplified: PDF handling now uses only PyMuPDF**, not two separate PDF
libraries. `pypdfium2` was only ever used for page-preview rendering;
PyMuPDF's own `get_pixmap()` does the same job, verified by actually
rendering a test page and visually confirming it wasn't blank before
removing the dependency. Neither library performs OCR — this change
doesn't gain or lose scanned-document support either way, which is worth
knowing since that was a point of real confusion going in.

2 new tests (40 total): one confirming the PDF renderer produces real,
non-blank page images after the library swap, and the EC2 axial-resistance
test updated for the corrected concrete-strength behavior.

**Deferred to a future session** (bigger scope, need dedicated focus):
unequal-span continuous beam analysis, column effective-length/end-condition
input, splitting app.py into a multi-page Streamlit app, print-ready CSS
for browser-to-PDF export, benchmark tests against the real RCC41/51/81/71
spreadsheets, and wiring the new cover setting into the Whole Building
Automated Design module specifically (that module's own file wasn't
touched this round to avoid a rushed, unreviewed change to code not fully
re-read this session).

## v25 — Fix column service-load double-counting bug

**Real bug, found from a user report, not a hypothetical.** Column
Design's `N_service` (which feeds Pad Footing Design's 🔗 "pull axial load"
link) was double-counting the beam's dead load (Gk) in the normal load
path — a leftover from a variable (`gk_total`) meaning two different things
across the module's "legacy" and normal load-input branches. The line
computing `N_service` was written for the legacy branch's meaning and
never updated when the normal branch was added.

**Impact**: for any ordinary dead-load-dominant column (Gk noticeably
larger than Qk — the normal case for most concrete buildings, not an edge
case), the service load could come out HIGHER than the ultimate load,
which Pad Footing Design correctly rejects as physically nonsensical
("Ultimate axial load should not be less than service axial load"). This
is exactly the bug reported: it reproduced on essentially every realistic
input, not intermittently.

**Fix**: `N_service` now adds the column's own self-weight only, since the
beam's service load (`N_serv_beams`) already includes the beam's Gk once,
correctly. Verified by hand-calculation match, not just "tests pass."

1 new regression test (39 total) that reproduces the exact reported
scenario and hand-verifies the corrected numbers, plus confirms the
legacy load path (which was already correct) remains unaffected.

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
