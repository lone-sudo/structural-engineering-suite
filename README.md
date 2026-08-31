# Structural RCC Suite

A Streamlit-based preliminary reinforced-concrete design and gravity-load
workflow.

## Important engineering status

This project is **not a construction-ready structural design package**.
Outputs are calculation aids and must be independently reviewed by a suitably
qualified structural engineer before construction, statutory submission, or
issue-for-construction use.

The application now distinguishes:

- `PASS` — an implemented check passed.
- `FAIL` — an implemented check failed.
- `NOT CHECKED` — the software deliberately does not claim that the check was performed.
- `WARNING` — a screening result requires engineering review.

A report containing `NOT CHECKED` items is **not a completed design**.

## Scope of the automated building workflow

The whole-building workflow represents a **single representative internal
gravity bay**:

`Two-way slab -> equal-span beam -> representative internal column -> pad footing`

It does not analyse an entire building frame, lateral system, wind/seismic
actions, differential settlement, load redistribution between arbitrary bays,
or foundation-soil interaction.

## Design standards

- **BS 8110** routines are retained for legacy projects. BS 8110 has been
  withdrawn in the UK; confirm the standard required by the project and local
  authority.
- **Eurocode 2** flexural resistance uses explicit design strengths and the
  rectangular stress-block approach for `fck <= 50 MPa`.
- The application does **not** claim that every analysis/detailing check is
  implemented for either code. The report identifies limitations explicitly.

## Load path

Permanent and variable actions are kept separate as `Gk` and `Qk` through the
gravity-load pipeline. Ultimate actions are formed only at the design stage:

`Ed = gamma_G * Gk + gamma_Q * Qk`

The previous implementation that split an already-factored slab reaction into
arbitrary 65%/35% dead/live components has been removed.

## Quantities and cost

Steel quantities are generated from the selected reinforcement and explicit
preliminary cut-length assumptions. No hard-coded steel tonnage is used.

The BBS is still a **preliminary quantity schedule**, not a final bar-bending
drawing. Laps, anchorage, curtailment, hooks, bends, wastage and project
detailing rules require engineer review.

## Security

No administrator key or plaintext PIN is stored in source code.

Configure:

```text
RCC_ADMIN_KEY=<long-random-secret>
```

using Streamlit Secrets or an environment variable. Never commit `.env`,
`licenses.json`, or real secrets.

For production, replace the local JSON license store with a proper database or
managed authentication service.

## Development

```bash
python -m pip install -r requirements.txt
pytest -q
python -m compileall .
streamlit run app.py
```

## Current limitations

The most important remaining engineering work is:

1. Full continuous-frame analysis for unequal spans and realistic load cases.
2. Complete EC2 shear and punching design.
3. Full BS 8110 footing punching design where BS 8110 is contractually required.
4. Column axial-moment interaction, biaxial bending and second-order effects.
5. Full serviceability design: deflection, cracking and long-term effects.
6. Detailed reinforcement anchorage, lap, curtailment and congestion checks.
7. Wind/seismic/lateral load analysis.
8. Comprehensive validation against independently calculated benchmark examples.


## Documentation

See `USER_GUIDE.md` for installation, workflow, verification-status meanings, slab selection, load-path interpretation and the engineering review checklist.
