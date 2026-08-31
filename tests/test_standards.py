import math

from core.standards import BS8110, Eurocode2


def test_bs8110_zero_moment_still_minimum_steel():
    r = BS8110.design_flexure(0, 1000, 125, 25, 460)
    assert r["As_req"] > 0


def test_ec2_uses_design_concrete_strength():
    r = Eurocode2.design_flexure(20, 1000, 125, 20, 460)
    assert r["f_cd"] > 0
    assert r["f_yd"] == 460 / 1.15


def test_ec2_rejects_high_strength_until_supported():
    try:
        Eurocode2.design_flexure(20, 1000, 125, 60, 460)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected explicit unsupported-strength error")
