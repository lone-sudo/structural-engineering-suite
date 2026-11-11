"""Screening wind pressure for the Phase-2 frame workflow.

This is a deliberately simple EN 1991-1-4-style estimate, not a full terrain/
orography/altitude calculation. It is useful for relative frame behaviour and
drift screening; the project wind consultant / National Annex remains the
authority.
"""
from __future__ import annotations

import math
from typing import Dict

RHO_AIR = 1.25  # kg/m3


def wind_pressure_kpa(
    vb_m_s: float, height_m: float, terrain: str = "suburban",
    cp_net: float = 1.3,
) -> Dict[str, float]:
    """Return basic velocity pressure qb, exposure factor ce and net pressure.

    ``cp_net`` = windward +0.8 plus leeward -0.5 by default. ``ce`` uses a
    simple power-law exposure profile with representative terrain factors.
    """
    if vb_m_s <= 0 or height_m <= 0:
        raise ValueError("Wind velocity and height must be positive.")
    terrain = terrain.lower()
    factors = {
        "open": (1.6, 0.14),
        "suburban": (1.4, 0.20),
        "urban": (1.2, 0.28),
    }
    if terrain not in factors:
        raise ValueError(f"Unsupported terrain category: {terrain}")
    c0, exponent = factors[terrain]
    ce = c0 * (max(height_m, 1.0) / 10.0) ** exponent
    qb_pa = 0.5 * RHO_AIR * vb_m_s ** 2
    qp_pa = ce * qb_pa
    w_kpa = qp_pa * cp_net / 1000.0
    return {
        "qb_kpa": qb_pa / 1000.0,
        "ce": ce,
        "qp_kpa": qp_pa / 1000.0,
        "w_kpa": w_kpa,
        "cp_net": cp_net,
        "terrain": terrain,
    }
