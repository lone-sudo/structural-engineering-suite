"""Design load combinations for gravity + wind screening.

EN 1990 combinations use the characteristic permanent action G, the leading
variable action Q or W, and psi factors for accompanying actions. BS 8110
combinations follow Table 2.1. These are screening combinations for the frame
workflow; project-specific National Annex / contract factors must be confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Combination:
    name: str
    kind: str  # "ULS" or "SLS"
    factors: Dict[str, float]


def en1990_combinations(
    psi0_q: float = 0.7, psi1_q: float = 0.5, psi2_q: float = 0.3,
    psi0_w: float = 0.6, psi2_w: float = 0.0,
) -> List[Combination]:
    g, q, w = 1.35, 1.5, 1.5
    return [
        Combination("ULS-1: 1.35G + 1.5Q", "ULS", {"G": g, "Q": q}),
        Combination("ULS-2: 1.35G + 1.5W", "ULS", {"G": g, "W": w}),
        Combination("ULS-3: 1.35G + 1.5Q + 1.5x0.6W", "ULS", {"G": g, "Q": q, "W": w * psi0_w}),
        Combination("ULS-4: 1.35G + 1.5W + 1.5x0.7Q", "ULS", {"G": g, "W": w, "Q": q * psi0_q}),
        Combination("SLS-1: G + Q", "SLS", {"G": 1.0, "Q": 1.0}),
        Combination("SLS-2: G + 0.6W", "SLS", {"G": 1.0, "W": psi0_w}),
        Combination("SLS-QP: G + 0.3Q", "SLS", {"G": 1.0, "Q": psi2_q}),
    ]


def bs8110_combinations() -> List[Combination]:
    return [
        Combination("ULS-1: 1.4G + 1.6Q", "ULS", {"G": 1.4, "Q": 1.6}),
        Combination("ULS-2: 1.4G + 1.4W", "ULS", {"G": 1.4, "W": 1.4}),
        Combination("ULS-3: 1.2G + 1.2Q + 1.2W", "ULS", {"G": 1.2, "Q": 1.2, "W": 1.2}),
        Combination("ULS-4: 1.0G + 1.4W", "ULS", {"G": 1.0, "W": 1.4}),
        Combination("SLS-1: G + Q", "SLS", {"G": 1.0, "Q": 1.0}),
        Combination("SLS-QP: G + 0.3Q", "SLS", {"G": 1.0, "Q": 0.3}),
    ]


def combinations_for(code: str) -> List[Combination]:
    if code == "Eurocode 2":
        return en1990_combinations()
    if code == "BS8110":
        return bs8110_combinations()
    raise ValueError(f"Unsupported design code: {code}")
