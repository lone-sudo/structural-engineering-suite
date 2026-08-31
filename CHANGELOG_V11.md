# Structural RCC Suite v11

## Fixes
- Fixed Streamlit form submission buttons in Continuous Beam, Column Takedown, and Pad Footing. They are now correctly inside their `st.form()` blocks.
- Clarified Whole Building terminology: `Building Storeys Above Ground`; use 1 for a single-storey building.
- Added explicit scope note that the current automated building model is a representative gravity bay, not a full arbitrary architectural/frame model.
- Removed generated Python cache/test-cache directories from the distribution to keep the package lightweight.

## Validation
- `pytest -q`: 15 passed
- `python -m compileall -q .`: passed
- Static check confirms all `st.form_submit_button()` calls are inside form indentation blocks.

## Known scope limitations to address in later versions
- Whole-building model currently represents one internal gravity bay and does not yet model arbitrary column/beam placement.
- 3D view is a structural schematic, not an architectural visualization.
- Ground-bearing slabs and buildings with no suspended floors need an explicit modelling option rather than being inferred from storey count.
