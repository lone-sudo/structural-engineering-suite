# Structural RCC Suite

A Streamlit workspace for preliminary reinforced-concrete design and
gravity-load take-down to **BS 8110-1:1997** and **EN 1992-1-1 (Eurocode 2)**.

> **Engineering status:** this is a calculation aid, not a construction-ready
> design package. Every result must be independently checked by a suitably
> qualified structural engineer before construction, statutory submission or
> issue for construction. A result containing `NOT CHECKED` items is not a
> completed design.

The tool deliberately distinguishes:

| Status | Meaning |
|---|---|
| `PASS` | An implemented check was performed and passed. |
| `FAIL` | An implemented check was performed and failed. |
| `NOT CHECKED` | The software does not claim to have performed this check. |
| `WARNING` | A screening result or applicability limitation needs engineering review. |

## Quick start

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

No licence key is required for the public build. Enforcement is opt-in for a
managed deployment with `RCC_REQUIRE_LICENSE=true` (plus `RCC_ADMIN_KEY` and a
licence store). See `.env.example`.

## What is implemented

- **Continuous beams** — arbitrary number of unequal spans, independent
  width/depth per span, a real slope-deflection matrix solution, and code
  pattern loading with the required `1.0Gk` minimum load on unloaded spans.
  BS 8110 and EC2 flexure, shear, minimum steel, span/depth deflection
  screening, one-layer bar-fit checks and link schedules. Optional T-beam
  sagging design uses an engineer-supplied effective flange width/thickness.
- **Columns** — axial take-down, BS 8110/EC2 axial resistance, minimum
  eccentricity, BS 8110 slender-column additional moments, EC2 slenderness
  (`λ` vs `λlim`) and nominal-curvature second-order moments, a
  strain-compatibility N-M interaction, code biaxial combination, and
  bar/links selection.
- **Pad footings** — service bearing sizing, ULS flexure, one-way shear and
  punching screening (BS 8110 1.5d / EC2 2d), buried-pad cover, and a
  rectangular-projection check.
- **Two-way slabs** — BS 8110 Table 3.14 coefficient method for nine panel
  types, corner/edge conditions, top and bottom steel, shear and deflection
  screening. Selecting EC2 changes the load factors and resistance, not the
  BS coefficient table (stated explicitly in the result).
- **One-way slabs and stairs** — simply-supported strip/flight checks covering
  flexure, shear, distribution steel, deflection and EC2 crack width.
- **Serviceability** — EC2 cracked-section steel stress and crack width
  (7.3.4) under the quasi-permanent combination for beams, slabs and stairs;
  EC2 anchorage and lap lengths (8.4/8.7) are reported for detailing.
- **3-D frame analysis** — a rigid-jointed regular-grid frame built from the
  structural grid: fixed bases, tributary slab loads, wind floor loads,
  EN 1990/BS 8110 load combinations, member-action envelope, base shear and
  drift screening.
- **Whole-building representative bay** — slab → continuous beam →
  representative internal column → pad footing, with a preliminary BBS,
  steel quantity/cost estimate and HTML/DXF exports.
- **Reporting** — per-element and combined HTML calculation sheets, DXF
  reinforcement details, and a project dashboard.

## Verification status

| Check | BS 8110 | EC2 |
|---|---|---|
| Beam flexure (rectangular) | ✅ | ✅ |
| Beam shear | ✅ | ✅ |
| Beam deflection (span/d screening) | ✅ | ✅ |
| Beam bar fit / links | ✅ (one layer) | ✅ (one layer) |
| Column axial resistance | ✅ | ✅ |
| Column slenderness | ✅ (additional moment) | ✅ nominal curvature (φef = 2.0 assumption) |
| Column N-M interaction | ✅ strain compatibility | ✅ strain compatibility |
| Column biaxial interaction | ⚠️ code equivalent-uniaxial rule | ⚠️ code exponent rule |
| Footing bearing / flexure | ✅ | ✅ |
| Footing one-way shear | ✅ (unreinforced) | ✅ (unreinforced) |
| Footing punching | ⚠️ 1.5d screening | ✅ 2d unreinforced |
| Two-way slab moments | ✅ BS Table 3.14 | ⚠️ BS coefficients used |
| Slab shear / deflection | ✅ | ✅ |
| Stair flexure / shear / deflection | ✅ | ✅ |
| Crack width | ❌ | ⚠️ quasi-permanent, EC2 7.3.4 |
| Anchorage / laps | ❌ | ⚠️ lengths reported, embedment not checked |
| Curtailment, hooks, bends | ❌ | ❌ |
| T-beam sagging flexure | ✅ effective flange input | ✅ effective flange input |
| 3-D frame / gravity + wind / drift | ✅ screening | ✅ screening |
| Load combinations (EN 1990 / BS 8110) | ✅ | ✅ |
| Seismic, flat slabs, foundations, torsion | ❌ | ❌ |

✅ implemented · ⚠️ implemented with a stated limitation · ❌ not implemented

The full engineering review — what works, what is unsafe or missing, what
should be removed, and a prioritised roadmap — is in
[`ANALYSIS.md`](ANALYSIS.md).

## Scope and load path

The **Frame Analysis (Phase 2)** module builds a regular-grid 3-D frame from
the geometry and analyses gravity + wind combinations. It assumes rigid
joints, fixed bases, no floor-diaphragm flexibility, no soil-structure
interaction and no seismic action; it is a screening model.

The separate **Whole Building Automated Design** workflow remains a
representative gravity bay:

`two-way slab → equal-span continuous beam → representative internal column → pad footing`

It does not analyse a complete frame, lateral system, wind/seismic actions,
differential settlement, arbitrary bay redistribution or soil-structure
interaction. Permanent and variable actions remain separate as `Gk` and `Qk`
until the design combination is formed:

`Ed = gamma_G * Gk + gamma_Q * Qk`

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q .
python -m pytest -q
python -m streamlit run app.py
```

The test suite includes hand-checkable benchmark cases (simply-supported and
continuous-beam theory, an RCC94 two-way slab example) plus regression tests
for every safety fix described in `ANALYSIS.md`.

## Documentation

- [`ANALYSIS.md`](ANALYSIS.md) — complete engineering and product review.
- [`USER_GUIDE.md`](USER_GUIDE.md) — workflow, status meanings and review checklist.
- [`USER_MANUAL.md`](USER_MANUAL.md) — detailed module reference.
- [`CHANGELOG.md`](CHANGELOG.md) — release history.
