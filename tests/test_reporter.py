from core.reporter import StructuralReporter


def test_bar_mass_formula():
    from core.rebar import RebarSelector
    assert abs(RebarSelector.UNIT_WEIGHT_KG_M[12] - (12**2 / 162)) < 1e-9
    assert abs(RebarSelector.UNIT_WEIGHT_KG_M[20] - (20**2 / 162)) < 1e-9


def test_tonnage_cost_includes_explicit_allowance():
    rows = [{"Diameter (mm)": 12, "Total Weight (kg)": 81.0}]
    out = StructuralReporter.calculate_tonnage_and_cost({}, 150000, rows, wastage_pct=5)
    assert out["total_kg"] == 81.0
    assert out["wastage_kg"] == 4.05
    assert out["procurement_kg"] == 85.05
    assert out["estimated_cost_kes"] == 12757.5
