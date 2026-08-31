# Structural RCC Suite — User Guide

## Purpose

Structural RCC Suite is a lightweight engineering workspace for reinforced-concrete design calculations. It is intended to reduce repetitive spreadsheet work while leaving the engineer in control of assumptions, geometry, member selection, interpretation, and final professional judgement.

The application is a calculation aid, not a substitute for an engineer's independent verification, drawings, specifications, or applicable statutory requirements.

## Getting started

1. Open PowerShell in the project folder.
2. Activate the existing virtual environment:
   `\.venv\Scripts\Activate.ps1`
3. Run the automated tests:
   `python -m pytest -q`
4. Compile-check the Python files:
   `python -m compileall -q .`
5. For local development testing, enable the temporary development-mode license bypass:
   `$env:RCC_DEV_MODE="true"`
6. Start Streamlit:
   `python -m streamlit run app.py`

Do not create a new virtual environment for every application revision if the existing environment already contains the required packages.

## Global project settings

Set the design code, concrete cube strength and reinforcement yield strength in the sidebar. These settings are shared by the design modules.

Current design-code choices are BS 8110 and Eurocode 2. The application should not be treated as demonstrating code compliance for checks that are explicitly marked NOT CHECKED.

## Module workflow

### CAD / PDF Drawing Importer

Use this module to extract available plan information and synchronise detected project values into the design workspace. Imported geometry should be reviewed by the engineer; drawing extraction is not assumed to be perfect.

### Whole Building Automated Design

Start by defining the structural grid in X and Y and selecting which grid intersections contain columns. The geometry drives the structural preview.

The current automated gravity calculation uses a representative internal bay. The geometry editor is therefore not yet a general finite-element or full-frame analysis engine. The interface states this limitation deliberately.

A single-storey building should be entered as **1** storey above ground. Storey count means the number of levels contributing to the supported column load in the current model.

### Beam Design

Enter span and loading assumptions and run the calculation. Review the analysis method, internal forces, reinforcement and verification status.

### Column Design

Review column geometry, supported storeys and beam-load assumptions. The displayed axial action is:

- **NEd** for Eurocode 2: design axial force.
- **Nu** for BS 8110: ultimate axial load.

These labels describe the design-code terminology; they should not be interpreted as column capacity. Capacity is reported separately where implemented.

### Pad Footing Design

Review column/load inputs, soil bearing capacity, footing dimensions and reinforcement. Do not treat a result as fully verified when a relevant check is marked NOT CHECKED.

### Slab Design

The module is intentionally named **Slab Design**, rather than Two-Way Slab. Select the slab type inside the module:

- **One-way slab** — preliminary simply-supported 1 m strip model.
- **Two-way slab** — BS 8110 Table 3.14 coefficient-method panel model.

For a one-way slab, the principal bending result is **Mu** for the design strip. Mx and My are two-directional quantities used by the two-way model and therefore are not expected outputs from the one-way model.

For a two-way slab, changing the panel/edge condition changes the moment coefficients and therefore the calculated moments and reinforcement. It does not change the underlying slab load merely because the support condition changed.

### Stair Design

Review geometry, loads, bending reinforcement and the serviceability screening result. A screening result is not equivalent to a full long-term serviceability analysis.

## Understanding verification statuses

- **PASS** — the implemented check was completed and the reported criterion passed.
- **FAIL** — the implemented check was completed and the reported criterion failed.
- **NOT CHECKED** — the software does not currently implement enough of that verification to claim compliance.
- **WARNING** — a calculation or applicability condition needs engineering review.
- **N/A** — the check does not apply to the selected case.

A NOT CHECKED result is not the same as a failed design. It means the software is deliberately refusing to make an unsupported compliance claim.

## Whole-building load path

The intended conceptual load path is:

Slab → Beam → Column → Footing → Soil.

The whole-building summary reports representative results along this path. Always confirm that the actual building's geometry, load distribution, openings, transfer conditions and support conditions are represented adequately before relying on the results.

## 3D structural preview

The 3D preview is a structural schematic. It is not an architectural rendering and is not intended to replace structural drawings.

In the current workflow the interactive 3D preview is placed at the bottom of the Whole Building page so that normal calculation/results scrolling is not interrupted by the interactive plot.

## Engineering review checklist

Before using a calculation in a project, confirm at minimum:

1. Correct design code and material strengths.
2. Correct geometry and support conditions.
3. Correct permanent and variable actions.
4. Correct load combinations.
5. Appropriate analysis method for the actual structural system.
6. All relevant strength checks are implemented and passed.
7. Serviceability checks are completed where required.
8. Reinforcement spacing, cover, anchorage, laps and detailing are checked.
9. Load paths and unusual conditions are reviewed independently.
10. Final drawings and calculations are reviewed and approved by the responsible engineer.

## Roadmap

The intended direction is to expand the slab selector and other member workflows without pretending unsupported calculations are complete. Future slab systems may include cantilever, flat, ribbed and waffle slabs once their appropriate analysis and detailing checks are implemented and validated.

## v17 quantity and cost estimate
The Whole Building report separates **BBS steel weight** from **procurement quantity**. The procurement quantity is the BBS weight plus an editable allowance for cutting/wastage. The allowance is a procurement assumption, not a structural design quantity. The steel rate is also editable because market prices change. Final ordering must use an engineer-reviewed BBS and supplier/project pricing.

## v17 visual layout
The parametric structural section drawings appear before the optional interactive 3D structural preview. The 3D preview is intentionally the last visual block so it cannot sit between later page content and intercept normal scrolling to content below it.
