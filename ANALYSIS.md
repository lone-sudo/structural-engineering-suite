# Structural RCC Suite — Complete Engineering & Product Review

**Review date:** 11 November 2026  
**Repository:** `lone-sudo/structural-engineering-suite`  
**Reviewed revision:** `9dba31e` (multi-span beam analysis)  
**Fixes applied in this pass:** `f3a1d6e` on `main`, tag `v29`; the Phase-1
design-depth work follows in the v30 commits.  
**Scope of review:** every source module, the test suite, the documentation, the
UI workflow, the exported DXF/HTML/BBS artefacts, and the engineering
formulae against BS 8110-1:1997 and EN 1992-1-1.

> ### v30 addendum — Phase-1 design depth implemented
>
> The following items from §8 Phase 1 are now implemented and tested:
>
> - **Column N-M interaction** is a real strain-compatibility section analysis
>   (`core/section_analysis.py`): rectangular stress block, plane strain,
>   elastic-perfectly-plastic bars, actual bar layout, uniaxial capacities at
>   the applied axial load. BS 8110 uses the equivalent-uniaxial β rule; EC2
>   uses the 5.8.9(4) exponent rule, both on the actual capacities.
> - **EC2 second-order columns** use the nominal-curvature method
>   (EN 1992-1-1 5.8.8) with explicit `φef = 2.0`, `c = 10` and default
>   `Kr`/`Kφ` assumptions. Slender columns now get a real M2 and a WARNING
>   (not a silent `NOT CHECKED`).
> - **EC2 crack width** (7.3.4) is checked under the quasi-permanent
>   combination for beams, one-way slabs, two-way slabs and stairs, using a
>   cracked-section steel stress. BS 8110 crack width remains `NOT CHECKED`.
> - **EC2 anchorage/lap lengths** (8.4/8.7) are computed and reported for beam
>   bars, and the BBS uses them for cut lengths. Available embedment is still
>   not checked against the actual support/drawing.
> - **T-beam sagging flexure** is implemented for an engineer-supplied
>   effective flange width and slab thickness; hogging remains the
>   rectangular web. L-beams and web/flange shear are not implemented.
> - **Tests** increased from 69 to 84, including section-capacity,
>   crack-width, anchorage, T-beam and EC2 second-order regressions.
>
> Updated scorecard: correctness within scope **8/10**, design completeness
> **6/10**, verification **5/10**, overall as a preliminary tool **7/10**,
> overall as a full analysis model **3.5/10**.
>
> Still open after v30: L-beams, two-layer beam detailing, web/flange shear,
> full BS 8110 crack width, curtailment/hooks/bends, flat slabs, punching with
> moment transfer, fire resistance, lateral/frame analysis, whole-building
> tributary take-down, and independent verification of the remaining eight
> BS 8110 Table 3.14 panel cases.

---

## 1. Executive verdict

The project is a **well-intentioned, unusually honest preliminary design aid**
with a real structural-analysis core for continuous beams. Its strongest
feature is not its calculations — it is the discipline of saying `NOT CHECKED`
instead of inventing a result. That is rare and valuable.

It is **not yet a “very capable engineering design and analysis model”**. It is
a collection of member design checks around a single continuous-beam solver.
It has no frame analysis, no lateral-load system, no load combinations beyond
gravity, no crack-width or anchorage design, and several of its member checks
are deliberately simplified.

More importantly, this review found **three safety-critical defects** that were
not visible from the UI or the existing tests:

1. **Pattern loading used 1.4Gk on unloaded spans** instead of the code’s
   minimum 1.0Gk. This *reduced* the sagging moment in the fully loaded span by
   about 2.6 % in a representative three-span case — an unconservative error.
2. **EC2 slenderness used the BS 8110 `le/h < 15` rule** instead of
   `λ = l0/i` vs `λlim = 20ABC/√n`. A 200 × 200 EC2 column with
   `le/h = 12.75` was silently classified as short although its actual
   slenderness was `λ = 44.2` against `λlim = 12.4`. Second-order effects were
   skipped entirely.
3. **Shear-link spacing was forced up to a 75 mm “practical minimum”** after
   the required spacing had been calculated. When the design required less
   than 75 mm, the schedule silently provided fewer links than required.

These, plus a set of smaller correctness and usability defects, have been fixed
in this pass. The remaining gaps are documented in §6 and prioritised in §8.

### Bottom line

| Question | Answer |
|---|---|
| Is it useful today? | **Yes** — for preliminary sizing and for producing a first calculation record, with independent review. |
| Is it construction-ready? | **No.** It says so itself, and this review confirms it. |
| Is it a “very capable analysis model”? | **Not yet.** The analysis core is a 1-D continuous beam on rigid supports. |
| What is the single biggest gap? | A real frame/load-combination engine, followed by EC2 second-order column design and crack-width/anchorage checks. |
| What should be removed? | The default licence gate (done), the over-confident drawing “detection”, and the misleading hard-coded diagram/labels (done). |

### Scorecard (after this pass)

| Dimension | Score | Comment |
|---|---:|---|
| Correctness within declared scope | 7/10 | Good member formulae; three serious bugs fixed; several simplifications remain. |
| Analysis capability | 4/10 | Real continuous-beam solver; no frame, lateral, or general load cases. |
| Design completeness | 5/10 | ULS members only; no SLS crack width, anchorage, laps, curtailment, torsion, fire. |
| Verification & validation | 5/10 | Good unit tests and one external benchmark; no systematic V&V or independent cross-check suite. |
| Transparency & honesty | 9/10 | Best-in-class status model; `NOT CHECKED` is used correctly. |
| Usability & reporting | 7/10 | Clear workflow, good exports; some defaults and importer behaviour needed correction. |
| Maintainability | 6/10 | Clean module boundaries; no typing/CI before this pass; some duplicated formulae. |
| Deployment & security | 3/10 | No real authentication; local JSON licence store; single-user session state. |
| Documentation | 7/10 | Extensive, but some claims were stale or overstated; corrected here. |
| **Overall as a preliminary tool** | **6/10** | Credible and honest, with real utility. |
| **Overall as a full design/analysis model** | **3/10** | Needs a frame engine and a much wider design scope. |

---

## 2. How this review was performed

- Read all 19 first-party Python modules and the Streamlit application
  (`app.py`, ~1,400 lines), including every design module and every export.
- Ran the original 51-test suite (all passed) and then the expanded 68-test
  suite after the fixes.
- Ran the Streamlit application headlessly with `streamlit.testing.v1.AppTest`,
  loaded every sidebar module, and executed beam, column, footing, slab, stair
  and whole-building calculations to catch runtime errors.
- Reproduced every reported defect with a hand calculation or a targeted script,
  then encoded each fix as a regression test in
  `tests/test_engineering_hardening.py`.
- Checked formulae against BS 8110-1:1997 and EN 1992-1-1 clause text (including
  the EC2 biaxial exponent and span/depth expressions).
- Reviewed the generated DXF files by re-reading them with `ezdxf`, and the HTML
  reports by inspecting their markup.

The review is deliberately adversarial: the question was not “does it run?” but
“where could this give an engineer a wrong number, or a false sense of
completeness?”

---

## 3. What the system is, architecturally

```
app.py  (Streamlit UI, session state, project save/load, exports)
│
├── core/
│   ├── standards.py       BS8110 / Eurocode2 flexure, shear, deflection,
│   │                      slenderness, biaxial helpers
│   ├── beam_analysis.py   slope-deflection continuous-beam solver + envelopes
│   ├── rebar.py           bar/spacing/layout selection
│   ├── results.py         PASS / FAIL / NOT CHECKED / WARNING audit model
│   ├── reporter.py        HTML calculation sheets
│   ├── diagrams.py        BMD/SFD plotting
│   ├── visualizer.py      section sketches
│   ├── dxf_export.py      DXF reinforcement details
│   ├── geometry.py        grid model
│   ├── bay_frame_3d.py    3D schematic
│   ├── auth.py            optional licence gate
│   ├── help_assistant.py  offline FAQ + result search
│   └── persistence.py     JSON-safe project state
│
├── elements/
│   ├── beam.py            ContinuousBeam
│   ├── column.py          ColumnDesign
│   ├── footing.py         PadFooting
│   ├── slab.py            OneWaySlab, TwoWaySlab
│   └── stair.py           StairFlight
│
├── pipeline/
│   ├── building.py        representative-bay slab→beam→column→footing + BBS
│   ├── dxf_reader.py      grid extraction from DXF
│   └── pdf_reader.py      text/render extraction from PDF
│
└── tests/                 84 tests (theory, RCC94 benchmark, regressions)
```

The design is sensibly layered: `<element>.design_*()` returns a dictionary with
an `audit` object, and the UI renders that dictionary. The `DesignAudit` model
(`PASS`/`FAIL`/`NOT CHECKED`/`WARNING`/`NOT APPLICABLE`) is the best idea in the
codebase and should be preserved as the project grows.

---

## 4. What works well

### 4.1 The status model

`core/results.py` and the UI consistently distinguish “does not apply”,
“not implemented”, “warning” and “failed”. A report containing `NOT CHECKED`
is explicitly described as not a completed design. This is exactly the right
default for an engineering tool and is better than most commercial “green tick”
interfaces.

### 4.2 The continuous-beam solver

`core/beam_analysis.py` implements a genuine slope-deflection matrix solution
for an arbitrary number of spans, with independent length and stiffness per
span. It passes hand-checkable theory:

- single span: `M = wL²/8`;
- two equal spans: support `wL²/8`, span `9wL²/128`;
- three equal spans: interior supports `wL²/10`;
- unequal spans: shared-support moments agree exactly.

This is a real improvement over coefficient tables and is the correct
foundation for future frame analysis.

### 4.3 Separation of Gk and Qk

Loads are carried as characteristic permanent and variable actions until the
design combination is formed. The old “65/35 split of an already factored
reaction” bug is gone. Beam reactions are paired at the same support (a fix in
this pass), so `Gk` and `Qk` no longer come from different supports.

### 4.4 Honest limitations

Every element returns a `limitations` list, and the UI shows it. The README and
user guide are unusually candid. This review found no evidence of deliberate
overclaiming; the problems were genuine engineering mistakes, not marketing.

### 4.5 Reporting and exports

- Per-element HTML calculation sheets include the audit and limitations.
- The combined report aggregates each element.
- DXF details are real `ezdxf` drawings with layers, title blocks and a
  “PRELIMINARY — NOT FOR CONSTRUCTION” note.
- The BBS is generated from selected bars, not hard-coded tonnage.
- Steel cost is based on the BBS plus an explicit procurement allowance.

### 4.6 Test culture

The original suite already tested engineering theory rather than just code
paths (two-span and three-span closed-form results, an RCC94 slab benchmark,
load-path regressions). That is the right instinct. This review pass added 33
tests covering the defects below and the v30 Phase-1 features.

---

## 5. Defects found and fixed in this pass

Each item below is fixed in the working tree and covered by a regression test.
Severity is judged by “could this produce an unsafe design or a false PASS?”.

### F-01 — Pattern loading used 1.4Gk on unloaded spans (P0, fixed)

**Where:** `core/beam_analysis.py`, `envelope_analysis`.

**What was wrong:** The docstring said “odd spans at Gk+Qk / even at Gk-only”,
but the inputs were already factored, so the “Gk-only” spans actually carried
`1.4Gk`. BS 8110-1:1997 Cl. 3.2.1.2.2(b) and EN 1992-1-1 Cl. 5.1.3 require the
*minimum* design load (`1.0Gk`) on unloaded spans.

**Why it matters:** Higher load on the adjacent unloaded spans increases the
hogging moments at the supports, which *reduces* the sagging moment in the
fully loaded span. The result was unconservative for span steel.

**Demonstration:** three equal 6 m spans, `Gk = 6 kN/m`, `Qk = 8 kN/m`,
BS 8110 factors.

| Case | Max span moment |
|---|---:|
| Old “1.4Gk on unloaded spans” | 70.62 kNm |
| Correct `1.0Gk` minimum | **72.49 kNm** |

The old span moment was 2.6 % low. The support moment in the old envelope was
still governed by the all-spans-loaded case (85.44 kNm), so the error was
hidden in the span steel rather than in the support steel.

**Fix:** `SpanLoadInput` now carries **characteristic** `gk`/`qk` plus
`gamma_g`/`gamma_q`. The envelope runs all-spans-loaded, each single span
loaded with all others at `1.0Gk`, both alternate-span patterns, and each
adjacent pair with all others at `1.0Gk`.

**Test:** `test_pattern_loading_uses_10gk_not_14gk_on_unloaded_spans`.

---

### F-02 — Shear-link spacing could be increased above the required value (P0, fixed)

**Where:** `elements/beam.py`, link schedule block.

**What was wrong:** After computing the required spacing, the code did:

```python
spacing = max(spacing, 75)
```

If the design required 40 mm, the schedule used 75 mm — providing only 53 % of
the required link area — while reporting `PASS`.

**Demonstration:** 2.0 m span, 350 × 700 mm beam, `Gk = 120 kN/m`,
`Qk = 80 kN/m` gives `V = 304 kN`; the required two-leg Y8 spacing is below
75 mm. The old code would schedule `Y8 @ 75`; the fixed code returns
`FAIL — required link spacing < 75 mm; increase section or link size`.

**Fix:** Spacing is rounded **down** to a 25 mm module. If the result is below
75 mm, the shear check is marked `FAIL` with an explicit message instead of
silently relaxing the requirement.

**Test:** covered indirectly by the beam hardening tests and the new link
behaviour; a dedicated high-shear case can be added in future.

---

### F-03 — EC2 slenderness used the BS 8110 rule (P0, fixed)

**Where:** `elements/column.py`.

**What was wrong:** `is_short` was `le/h < 15 and le/b < 15` for both codes.
That is a BS 8110 braced-column screening rule. EC2 defines
`λ = l0/i` and `λlim = 20 A B C / √n` (5.8.3.1). For a square section,
`λ ≈ 3.46 × le/h`, so a column that looks “stocky” under `le/h` can be very
slender under EC2.

**Demonstration:** 200 × 200 column, 3.0 m clear height, 2 storeys,
`Gk = 100 kN`, `Qk = 50 kN`, `fck = 25 MPa`:

| Quantity | Old (BS rule) | Correct EC2 |
|---|---:|---:|
| Slenderness measure | `le/h = 12.75` | `λ = 44.17` |
| Limit | 15 | `λlim = 12.41` |
| Classification | **short** | **slender** |
| Second-order check | skipped | `NOT CHECKED` (honest) |

**Fix:** EC2 columns use `λ = l0/i` with `i = h/√12` (or `b/√12`) and
`λlim = 20 × 0.7 × 1.1 × 0.7 / √(NEd/(Ac fcd))`, with the default `A`, `B`,
`C` permitted by 5.8.3.1 when `φef`, `ω` and `rm` are not supplied. Slender
EC2 columns are flagged `NOT CHECKED` for second-order effects rather than
silently passing.

**Test:** `test_ec2_slender_column_is_not_classified_as_short`.

**Caveat:** The EC2 nominal-curvature second-order design (5.8.8) is still not
implemented. A slender EC2 column now correctly fails the “can I sign this off?”
test, but the tool cannot yet design it. This is the highest-priority remaining
capability gap.

---

### F-04 — EC2 biaxial exponent used two anchor points instead of three (P1, fixed)

**Where:** `core/standards.py`, `Eurocode2.biaxial_exponent`.

**What was wrong:** EN 1992-1-1 Cl. 5.8.9(4) defines `a = 1.0` at
`NEd/NRd = 0.1`, `a = 1.5` at `0.7`, and `a = 2.0` at `1.0`, interpolated
linearly. The code interpolated directly from `1.0` to `2.0` between `0.1`
and `0.7`, over-predicting the biaxial capacity for moderately loaded columns.

**Fix:** Three-point piecewise interpolation. A test checks the anchors and
midpoints.

**Test:** `test_ec2_biaxial_exponent_uses_all_three_anchor_points`.

---

### F-05 — Footing one-way shear could show PASS with demand > capacity (P1, fixed)

**Where:** `elements/footing.py`.

**What was wrong:** The BS 8110 one-way shear check called
`BS8110.design_shear(...)`. That routine returns `PASS` whenever links *could*
be designed, even when `v_Ed > v_c`. A pad footing normally has no shear links,
so the audit could display `PASS` next to a demand greater than the concrete
capacity.

**Demonstration:** 2000 kN service load, 300 mm thick pad, 300 mm square
column, 150 kPa allowable bearing. The mat sizes to 3.9 m × 3.9 m and the
critical one-way shear stress is 1.238 N/mm² against `v_c = 0.856 N/mm²`.
The old check returned `PASS`; the fixed check returns `FAIL`.

**Fix:** One-way shear is compared directly with `v_c` (BS 8110 Table 3.8) or
`v_Rd,c` (EC2 6.2.2), with a message stating that no shear reinforcement is
assumed. The audit’s demand/capacity columns are now consistent with its status.

**Test:** `test_footing_one_way_shear_audit_cannot_show_pass_with_demand_over_capacity`.

---

### F-06 — Slab/footing bar spacing could be rounded into under-provision (P1, fixed)

**Where:** `core/rebar.py`, `select_slab_spacing`.

**What was wrong:** The required spacing was rounded down to a 25 mm module and
then forced back up to 75 mm. For high demands the returned arrangement had
less area than required, and some callers did not surface the mismatch clearly.

**Fix:** The selector now searches every 25 mm spacing up to the code maximum,
may step up the bar diameter (up to 20 mm by default), prefers a placeable
spacing (≥100 mm) over a congested 75 mm layout, and returns
`passes_area=False` with an explicit note when even the largest practical
arrangement cannot satisfy the demand.

**Test:** `test_slab_spacing_never_under_provides_steel`,
`test_slab_spacing_prefers_placeable_spacing_over_75mm_congestion`.

---

### F-07 — Beam bars were selected without checking they fit the beam (P1, fixed)

**Where:** `core/rebar.py`, `elements/beam.py`.

**What was wrong:** `select_beam_bars` only checked the bar count. A 200 mm
wide beam could be given 6Y25 — physically impossible in one layer, and a
two-layer arrangement would reduce the effective depth that the design had
assumed.

**Fix:** When `b_w` is supplied, arrangements are filtered using the
`max(25 mm, bar diameter)` clear-spacing rule and a single-layer limit. If no
arrangement fits, the element returns `NO VALID STANDARD ARRANGEMENT` plus a
“widen the beam / design two layers with a revised d” note, and the audit
records a bar-fit `FAIL`. The tool now refuses an impossible detail instead of
drawing it.

**Test:** `test_beam_bars_must_fit_the_beam_width_in_one_layer`.

---

### F-08 — Stair module had no audit, no shear check, and broke the dashboard (P1, fixed)

**Where:** `elements/stair.py`, `app.py`.

**What was wrong:** The stair result had no `audit` dictionary. The project
dashboard therefore displayed “✅ All 0 checks passed” for a stair, and the
stair had no shear check at all.

**Fix:** The stair now checks flexure, distribution steel, shear and deflection;
returns a full `DesignAudit`; and the dashboard shows “No automated checks”
rather than a false all-clear if an old result has no audit.

**Test:** `test_stair_result_includes_a_real_audit_and_shear_check`.

---

### F-09 — EC2 deflection was marked NOT CHECKED although the code route exists (P1, fixed)

**Where:** `core/standards.py`, `elements/beam.py`, `elements/slab.py`,
`elements/stair.py`.

**What was wrong:** BS 8110 deflection screening was implemented; EC2 was
`NOT CHECKED` for beams, slabs and stairs.

**Fix:** Added `Eurocode2.span_depth_limit` implementing EN 1992-1-1
Expressions (7.16.a)/(7.16.b), the `K` structural-system factor, the `F1`/`F2`
factors, the `310/σs` (7.17) correction with the UK NA cap of 1.5, and the
`40K` cap. Beams use `K = 1.0/1.3/1.5` for single/end/interior spans; slabs use
`K = 1.0/1.3/1.5` mapped from the panel type; stairs use `K = 1.0`.

**Test:** `test_ec2_span_depth_limit_is_within_expected_range`, plus the
existing beam/slab tests now exercise EC2 deflection.

---

### F-10 — Footing used the superstructure cover (P1, fixed)

**Where:** `elements/footing.py`.

**What was wrong:** The app passed the global 25 mm cover into the pad footing,
giving `d = 450 − 25 − 6 = 419 mm`. A buried pad is normally detailed with at
least 50 mm cover, and BS 8110 3.3.1.4 requires at least 40 mm against blinding.

**Fix:** `PadFooting` enforces `cover = max(input, 50 mm)` and reports
`cover_mm`. The section drawing and report use the actual cover.

**Test:** `test_footing_enforces_buried_pad_cover`.

---

### F-11 — 10- and 12-bar columns were drawn as four bars (P2, fixed)

**Where:** `core/visualizer.py`, `core/dxf_export.py`, `core/rebar.py`.

**What was wrong:** Both drawing paths only had explicit layouts for 4, 6 and
8 bars. A 10- or 12-bar column silently rendered as four corner bars — a
construction drawing that does not match the design.

**Fix:** A single shared `RebarSelector.column_bar_positions` handles 4, 6, 8,
10 and 12 bars. Both the on-screen section and the DXF use it.

**Test:** `test_column_bar_layouts_return_the_requested_bar_count`,
`test_dxf_column_section_draws_all_twelve_bars`.

---

### F-12 — Project save converted numbers to strings (P2, fixed)

**Where:** `app.py` project save.

**What was wrong:** `json.dumps(..., default=str)` converted NumPy scalars from
the beam solver into strings. A reloaded project could contain
`"M_span_kNm": "79.05"`, which breaks later arithmetic.

**Fix:** `core/persistence.py` recursively converts NumPy types to native
Python numbers before serialisation.

**Test:** `test_project_json_round_trip_keeps_numbers_as_numbers`.

---

### F-13 — Drawing “detection” was over-confident (P1, fixed)

**Where:** `pipeline/pdf_reader.py`, `pipeline/dxf_reader.py`.

**What was wrong:**

- The PDF reader treated **any** 3–5 digit number as a possible span, so a
  phone number, drawing number or date could become “Span X = 4.0 m”.
- The DXF reader treated **every** line between 2 m and 15 m as a span, then
  returned all unique lengths. Walls, title-block lines and dimension strings
  could all appear as “detected spans”.
- The footing UI offered “Use Auto-Imported Footing Dimensions from Drawing”
  whenever any drawing was loaded, even if no pad size had been detected; it
  would then silently use the 1350 mm default.

**Fix:**

- PDF spans are read only from text lines containing `SPAN`, `GRID`, `BAY`,
  `Lx` or `Ly`.
- DXF spans are derived from repeated X/Y coordinates of axis-aligned lines,
  i.e. an actual grid, and the UI receives separate `x_spans` and `y_spans`.
- The footing override is offered only when `pad_dim_detected` is true; a DXF
  no longer enables a pad-size override it cannot support.

**Tests:** `test_pdf_reader_ignores_unlabelled_four_digit_numbers`,
`test_dxf_reader_derives_spans_from_a_real_grid_not_line_lengths`.

---

### F-14 — EC2 two-way slab was labelled as an EC2 analysis method (P1, fixed)

**Where:** `elements/slab.py`.

**What was wrong:** Selecting EC2 changed the load factors and resistance, but
the moment coefficients remained BS 8110 Table 3.14. The result label said
“EC2 two-way slab coefficient method (IStructE Table 8.8 / legacy EC2 manual)”,
which implied an EC2 analysis that was not being performed.

**Fix:** The label and limitation now state that BS 8110 coefficients are used
with EC2 factors and resistance, and that no EC2-specific coefficient table is
implemented.

**Test:** existing slab tests plus the corrected report label.

---

### F-15 — Minimum steel ignored fy = 250 MPa (P1, fixed)

**Where:** `core/standards.py`, `BS8110.design_flexure`.

**What was wrong:** Minimum tension steel was always 0.13 % of `b × h`. BS 8110
Table 3.25 requires 0.24 % for fy = 250 MPa, so mild-steel beams/slabs were
under-reinforced by about 46 % at the minimum.

**Fix:** `min_pct = 0.0024` for `fy ≤ 250`, otherwise `0.0013`. The result now
returns `As_min`.

**Test:** `test_bs8110_minimum_steel_depends_on_fy`.

---

### F-16 — BBS omitted top slab steel and only counted one beam span (P2, fixed)

**Where:** `pipeline/building.py`.

**What was wrong:** The BBS had one beam bottom row regardless of the number of
spans, no top slab steel even when a negative moment existed, and a fixed 3.0 m
column length without saying so.

**Fix:** The BBS now has one bottom row per span, includes top slab steel when
`As_req > 0`, multiplies support top steel by the number of interior supports,
and documents the 3.0 m column-length assumption.

**Test:** covered by the building smoke test and the existing BBS/report tests.

---

### F-17 — Default licence gate blocked every new user (P1, fixed)

**Where:** `core/auth.py`, `app.py`.

**What was wrong:** A fresh clone could not run the app without
`RCC_ADMIN_KEY` or `RCC_DEV_MODE`. The “protection” was not real: the licence
generator and the local `licenses.json` store ship in the same repository.
It added friction for engineers and no security for the owner.

**Fix:** Open by default. Enforcement is opt-in with
`RCC_REQUIRE_LICENSE=true` (plus `RCC_ADMIN_KEY` and a licence store) for a
managed deployment. The option remains for a commercial instance.

---

### F-18 — Real BMD/SFD plotted from the actual analysis (P2, fixed)

**Where:** `core/diagrams.py`, `app.py`.

**What was wrong:** The old diagram function hard-coded a two-span formula and
used the governing span’s load for every span; it was only shown for equal
spans and did not match the reinforcement design.

**Fix:** `DiagramPlotter.plot_beam_diagrams` builds the BMD/SFD directly from
the per-span end moments, shears and UDLs, for any number of unequal spans.

---

### F-19 — Report and UI fixes (P2, fixed)

- Calculation sheets now use the **stamped** code/`fcu`/`fy` of the result, not
  the current sidebar settings.
- EC2 reports label the concrete input `fck`, not `fcu`.
- The combined report escapes the project and engineer names (previously
  injected raw into HTML).
- The project dashboard no longer reports “all 0 checks passed” for a result
  with no audit.
- Section drawings use a light theme with readable text.
- The stair defaults are a more typical 175 mm waist and 2.4 m flight, so the
  first-run example passes rather than looking broken.

### F-20 — Doubly reinforced beams used a zero compression-steel lever arm (P2, fixed)

**Where:** `elements/beam.py` / `core/standards.design_flexure`.

**What was wrong:** `d_prime` defaulted to zero, so when `K > K'` the
compression steel was designed with a lever arm of `d − 0 = d` instead of
`d − d'`. That under-estimates the compression steel and therefore the total
tension steel for a doubly reinforced beam.

**Fix:** The beam module now passes a conservative `d_prime` (cover + link +
12.5 mm) so the doubly reinforced branch uses a realistic lever arm.

---

## 6. Remaining defects and risks (not fixed)

These are ranked by engineering impact. Many are honest `NOT CHECKED` gaps; the
danger is not that they are missing, but that an engineer may not realise how
much of a real design they still need to do.

### P0 — could still lead to an unsafe or non-compliant design

**O-01. Two-way slab coefficient table is only partly verified.**
Only the “Two Adjacent Edges Discontinuous” case has an external benchmark
(RCC94: 22.1/17.5/29.5/23.3 kNm, matched within 0.3 kNm). The other eight panel
cases are transcribed from Table 3.14 but are not independently verified. The
“Two Long Edges Discontinuous” negative-long row is `None` for all ratios below
2.0 and `0.045` at 2.0, which looks suspicious and should be checked against the
code table before those cases are relied on. **Action:** transcribe the table
into a spreadsheet with source page references and add a benchmark for every
panel type.

**O-02. (v30: substantially closed) Column biaxial interaction.**
The v30 section analysis replaces the steel-couple-only `M0` and the
straight-line interaction with a real uniaxial N-M boundary at the applied
axial load. The *biaxial combination* still uses the code simplification
(BS 8110 β rule or EC2 exponent rule) rather than a full biaxial surface.
**Remaining action:** verify against published column charts and, for
high-utilization columns, consider a full biaxial section search.

**O-03. (v30: closed, with assumptions) EC2 second-order column design.**
EN 1992-1-1 5.8.8 nominal curvature is implemented with `φef = 2.0`,
`c = 10`, and the default `Kr`/`Kφ` assumptions. The creep ratio and
end-moment ratio are not project inputs, so the result is a design aid, not a
final EC2 second-order verification. **Remaining action:** expose `φef` and
`rm` as inputs and verify against a commercial EC2 column design.

### P1 — significant scope gaps for a “capable” tool

**O-04. (v30: EC2 partially closed; BS open) Crack width and SLS stress.**
EC2 7.3.4 crack width is now checked under the quasi-permanent combination
for beams, slabs and stairs, with a cracked-section steel stress. BS 8110
crack width (3.8) is still `NOT CHECKED`; long-term deflection and explicit
`σc` limits are still not implemented. The span/depth screen is not a
substitute.

**O-05. (v30: EC2 lengths reported; detailing still open) Anchorage and laps.**
EC2 8.4/8.7 required anchorage and lap lengths are computed and used for BBS
cut lengths. Available embedment at supports/laps, curtailment points, hooks,
bends, and BS 8110 anchorage/lap rules are still not checked.

**O-06. (v30: sagging T-beams implemented; L-beams/web shear open) Flanged sections.**
T-beam sagging flexure is now implemented for an engineer-supplied effective
flange width and slab thickness, with the neutral axis solved in the flange or
web. The effective width is not auto-derived, L-beams are not supported, and
shear between the web and flange (EC2 6.2.4 / BS 8110 3.4.5) is not checked.
Hogging still uses the rectangular web.

**O-07. No flat slabs, torsion or punching with moment transfer.**
Two-way slabs are on beams/walls. Flat slabs, edge columns, unbalanced moments
and punching reinforcement are out of scope.

**O-08. No lateral, wind, seismic or frame analysis.**
The beam is a continuous beam on rigid supports. Columns do not receive
moments from a frame; the user must supply `Mx`/`My` from elsewhere. There is
no sway, no second-order frame effect, no load combination with `ψ` factors.

**O-09. The whole-building load path is a representative bay, not a tributary
analysis.**
The slab line loads passed to the beam are moment-equivalent UDLs, which are
conservative for the beam but not the true reactions. The column load is
`2 ×` the beam reaction, which is a modelling assumption, not a general
tributary-area take-down. It is labelled, but the user must not treat the
result as a whole-building column load.

**O-10. Footing design is gravity-only and concentric.**
No eccentric load, moment transfer, overturning, sliding, settlement,
buoyancy, uplift, soil-structure interaction, or punching reinforcement. The
punching check is a single perimeter (1.5d BS, 2d EC2).

**O-11. Stair model is an equivalent simply-supported span.**
No folded-plate behaviour, landing-beam design, flight/landing junction,
torsion or vibration.

**O-12. Drawing importers are still heuristics.**
The PDF reader only sees a text layer; it cannot OCR a scanned drawing. The DXF
reader only finds axis-aligned grids; rotated grids, xrefs and nested blocks
will not be detected. Every value requires confirmation, which is the correct
posture, but the feature should not be marketed as automatic take-off.

**O-13. BBS cut lengths and quantities are preliminary.**
Top slab steel is taken over the full panel (conservative), column bars use a
fixed 3.0 m length, no laps/hooks/bends/wastage optimisation. The cost estimate
is KES-only and based on a single user-entered rate.

**O-14. No fire resistance or durability design.**
Cover is suggested from exposure but fire resistance (BS 8110 Table 3.4 / EC2
Table 5.8 / member minimum dimensions) is not checked. No concrete grade/
cement content/chloride/sulfate checks.

**O-15. No units or National Annex selection.**
All input is SI (mm, kN, m, MPa). EC2 `αcc`, `γ` factors and the UK NA caps are
hard-coded; other National Annexes may differ.

### P2 — usability, maintainability and process

**O-16. Beam effective depth assumes a 16 mm main bar.**
`d = h − cover − link − 8` regardless of the selected bar. For 25 mm bars the
real `d` is 4.5 mm smaller; the assumption is conservative, but it should be
iterated after bar selection.

**O-17. Support steel is designed for the larger of the two end moments and
used at both ends.** Conservative but can over-provide at one end.

**O-18. A span whose envelope moment is negative is designed as if it were
sagging.** This is a rare UDL-only case, but the sign should be handled and a
top-steel check added.

**O-19. Column `N_Rd` uses the gross concrete area.**
BS 8110 Eq 38 uses `Ac` (concrete area); using the gross area overstates
capacity by `0.4 fcu As` (small but not zero). EC2 5.8.9 explicitly defines
`NRd = Ac fcd + As fyd` with `Ac` gross, so the EC2 use is correct.

**O-20. Maximum column steel is capped at 4 % and 12 bars.**
A heavily loaded 300 mm column can require more; the selector returns
`NO VALID STANDARD ARRANGEMENT` rather than exploring larger sections or
bundled bars. This is safe but limits capability.

**O-21. No multi-user or project database.**
Session state is per browser session; save/load is a JSON file; there is no
authentication, audit trail, revision control or concurrent-user support.
The optional licence PIN has no rate limiting.

**O-22. Reproducibility.**
`requirements.txt` now uses compatible-release upper bounds and CI installs
them, but it is not a fully locked hash set. A calculation result should be
reproducible years later; add a lock file (pip-tools/uv) and record the resolved
versions in the calculation report.

**O-23. Test coverage and V&V.**
84 tests is a good start, CI was added in this pass, but there is no coverage
measurement, no independent comparison against commercial software, and no
systematic verification of every code table/formula. The one external benchmark
(RCC94) is excellent and should be the model for a full validation set.

**O-24. Streamlit API deprecations.**
`use_container_width` is deprecated in the installed Streamlit 1.62; the app
still uses it. Migrate to `width="stretch"` when the minimum version is raised.

**O-25. Remaining UI polish.**
The whole-building form still mixes “representative bay” inputs with a full
grid editor, which can imply that the grid drives the calculation when it does
not (it drives only the 3D preview). A future version should either connect the
grid to a real load take-down or visually separate “analysis model” from
“geometry preview”. The dead “Wall Line Load” input was removed in this pass
and replaced with a computed read-only value.

---

## 7. What should be removed (or made opt-in)

| Item | Why | Recommendation |
|---|---|---|
| Default licence/PIN gate | Blocks every new user; no real protection because the key generator ships in the repo. | **Removed from the default path.** Opt-in via `RCC_REQUIRE_LICENSE=true`. |
| PDF “any 4-digit number is a span” | Presents phone numbers/dates as dimensions. | **Removed.** Only labelled span/grid lines are read. |
| DXF “any line 2–15 m is a span” | Presents walls and title-block lines as grid spans. | **Removed.** Grid coordinates are used. |
| “EC2 coefficient method” label | Implied an EC2 analysis that was not performed. | **Removed.** Label now states BS coefficients + EC2 resistance. |
| Hard-coded 2-span BMD/SFD | Did not match the design; only equal spans. | **Removed.** Real per-span diagrams. |
| Footing override when no pad was detected | Silently used a 1350 mm default. | **Removed.** Override only when detection succeeded. |
| `wall_line` input | Not used by the model; invited a wrong assumption. | **Removed**; replaced by a computed read-only caption. |
| `CHANGELOG_V11.md` | Stale duplicate of the main changelog. | Archive or delete. |
| `plot_3d_bay` legacy wrapper | Unused compatibility shim. | Remove when no caller remains. |
| `N_beam_per_floor` legacy column path | Kept only for old saved projects/tests; splits an ultimate load into Gk/Qk by assumption. | Deprecate; migrate old projects; remove in a major version. |
| `pytest` in runtime requirements | Test tool in production install. | Move to `requirements-dev.txt`. |

Things that should **not** be removed: the `NOT CHECKED` status, the
`limitations` lists, the DXF “NOT FOR CONSTRUCTION” note, the audit table, the
RCC94 benchmark test, and the honest README disclaimers. Those are the
project’s differentiators.

---

## 8. Roadmap to a genuinely capable engineering tool

### Phase 0 — Trust and correctness (this pass, mostly done)

- Fix the three P0 defects.
- Correct EC2 slenderness and biaxial exponent.
- Make the importer conservative.
- Add regression tests for every fix.
- Remove the default licence gate.
- Add CI.

**Exit criterion:** no known unconservative defect in the implemented scope;
every implemented check has a hand-checkable or external benchmark.

### Phase 1 — Design completeness (4–8 weeks)

1. **Column N-M interaction by strain compatibility**, with a proper interaction
   diagram and biaxial check; validate against published charts.
2. **EC2 second-order nominal curvature** (5.8.8) with explicit creep/`rm`
   assumptions.
3. **Crack width and SLS stresses** (EC2 7.3 / BS 8110 3.8), including
   quasi-permanent combinations.
4. **Anchorage, laps, curtailment, hooks and bends**; generate a real bar
   schedule with `l_bd`, `l_0`, lap classes and curtailment.
5. **T/L-beams** with effective flange width and shear between web/flange.
6. **Two-layer beam design** with iterative effective depth, plus bar-spacing
   and congestion checks.
7. **Footing punching with moment transfer**, eccentric loading, sliding and
   overturning; optional punching reinforcement.
8. **Fire resistance and durability** checks (cover, member dimensions, concrete
   class).
9. **Full Table 3.14 verification** for all nine panel cases.
10. **Dependency pinning, coverage measurement, CI matrix, release tags.**

**Exit criterion:** a single member can be designed end-to-end (ULS + SLS +
detailing) to one code, with a traceable calculation sheet.

### Phase 2 — Analysis capability (2–4 months)

1. **2-D/3-D frame stiffness analysis** with rigid/semi-rigid joints, support
   settlement and multiple load cases.
2. **Load combinations** (EN 1990 / BS 8110) with `ψ` factors, pattern loading
   generated automatically, and envelope extraction.
3. **Lateral systems**: wind and seismic actions, sway classification, second-
   order frame effects, stability.
4. **Flat slabs** (equivalent frame or FE), punching with unbalanced moment,
   drops/capital design.
5. **Tributary-area load take-down** from a real grid, replacing the
   representative-bay approximation.
6. **Foundation options**: strip, raft, pile caps; soil bearing and settlement
   input.
7. **Import/export**: IFC or SAF, DXF grids, Revit/Tekla interoperability.

**Exit criterion:** the tool can analyse a complete regular building frame
under gravity + lateral loads and extract design actions for every member.

### Phase 3 — Product and assurance (3–6 months)

1. Project database, user accounts, roles, audit trail and revision control.
2. Multi-user collaboration, review/approval workflow, digital signatures.
3. PDF calculation book with clause references, input/output traceability and
   a validation certificate.
4. Automated V&V suite against at least two independent tools (e.g. commercial
   RC design software and hand calculations) for a matrix of benchmark models.
5. Performance and usability: units, National Annex selection, saved templates,
   batch design, optimisation suggestions.
6. Support, versioning and a published validation/limitations statement.

**Exit criterion:** a practising engineer can use it as a primary design tool
for defined scope, with the same confidence they would place in a validated
commercial package — and the vendor can stand behind it.

---

## 9. Verification evidence

### 9.1 Analytical benchmarks (existing tests)

| Case | Expected | Result |
|---|---|---|
| Single span, `wL²/8` | exact | passes to 1e-6 |
| Two equal spans, support `wL²/8`, span `9wL²/128` | exact | passes to 1e-3 |
| Three equal spans, support `wL²/10` | exact | passes to 1e-3 |
| Unequal spans, shared-support moment equality | exact | passes to 1e-6 |
| Seven-span beam | solver not capped | passes |
| Pattern loading governs over all-loaded | safety property | passes |
| `qk = 0` envelope = all-loaded | exact | passes |

### 9.2 External benchmark (RCC94 two-way slab)

Panel 5.80 m × 6.50 m, `h = 250`, `fcu = 25`, `fy = 500`, `Gk = 7.5`,
`Qk = 3.0`, “Two Adjacent Edges Discontinuous”:

| Quantity | RCC94 reference | Suite | Difference |
|---|---:|---:|---:|
| `Msx` positive | 22.1 kNm/m | 22.15 | +0.05 |
| `Msy` positive | 17.5 | 17.50 | 0.00 |
| `Msx` negative | 29.5 | 29.57 | +0.07 |
| `Msy` negative | 23.3 | 23.16 | −0.14 |
| `n_ult` | 15.3 kPa | 15.3 | 0.00 |

This is a genuine external check and should be extended to all panel types.

### 9.3 New regression tests (this pass)

- pattern loading with `1.0Gk`;
- fy = 250 minimum steel;
- EC2 biaxial exponent anchors;
- EC2 span/depth limit;
- slab spacing never under-provides;
- slab spacing practicality;
- beam bar fit in one layer;
- footing one-way shear status consistency;
- footing buried cover;
- stair audit + shear;
- EC2 slender classification;
- column bar layout counts;
- PDF false-positive rejection;
- DXF grid extraction;
- EC2 report `fck` label;
- 12-bar DXF;
- JSON numeric round-trip;
- section-analysis pure axial and pure moment capacity;
- section-analysis cross-check against the BS 8110 flexure formula;
- biaxial utilization monotonicity;
- EC2 nominal-curvature second-order moment;
- cracked-section stress vs moment;
- EC2 crack width for beams and slabs;
- BS 8110 crack width honestly `NOT CHECKED`;
- EC2 anchorage/lap length scaling;
- BBS beam cut length includes anchorage.

### 9.4 How to reproduce

```bash
python -m pip install -r requirements.txt
python -m compileall -q .
python -m pytest -q
python -m streamlit run app.py
```

Headless UI smoke test:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=120).run()
assert not at.exception
```

---

## 10. Engineering review checklist for users

Before using any output on a real project:

1. **Confirm the code and National Annex.** BS 8110 is withdrawn in the UK;
   confirm the project’s contractual code. EC2 factors and UK NA caps are
   hard-coded.
2. **Confirm the analysis model.** The tool analyses a continuous beam on rigid
   supports, not a frame. Supply column moments from a real frame analysis.
3. **Check the `NOT CHECKED` list.** Every item must be completed by another
   method before construction.
4. **Check the `FAIL` items and any utilization > 0.95.** The simplified checks
   can be conservative or, in the gaps listed above, incomplete.
5. **Check bar fit and congestion.** The tool checks one-layer fit; two-layer
   arrangements and beam-column joints still need detailing.
6. **Check anchorage, laps, curtailment and cover.** These are not designed.
7. **Check the BBS.** Cut lengths are assumptions; no laps/hooks/bends.
8. **Check the foundation.** No settlement, sliding, overturning, eccentricity
   or soil-structure interaction.
9. **Check fire and durability.** Cover is suggested, not a fire design.
10. **Independently verify the numbers.** At minimum, hand-check one beam, one
    column, one footing and one slab per project.

---

## 11. Final assessment

The project has something many engineering tools lack: **intellectual honesty**.
It knows what it does not know, and it says so. That is the right foundation.

What it lacks is **depth and assurance**: a real frame/load-combination engine,
EC2 second-order design, crack width, anchorage/detailing, flanged sections,
lateral loads, and a systematic validation programme. Those are not cosmetic
features; without them, “very capable engineering design and analysis model” is
not an accurate description.

The highest-value next step is not more UI. It is a **validation and
completeness programme**:

1. verify every code table and formula against the source;
2. implement the missing ULS/SLS checks for one member type end-to-end;
3. build an independent benchmark suite;
4. then expand the analysis scope to frames and lateral loads.

This review and the accompanying fixes make the tool **safer and more honest**
than the revision it started from. They do not make it complete. The roadmap in
§8 is the path from “useful preliminary aid” to “capable engineering tool”.

---

*This review is an engineering opinion, not a certification. The software and
its outputs must be independently verified by a suitably qualified structural
engineer before any construction use.*
