from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class GridGeometry:
    """Lightweight structural grid/column model used by the UI and 3D preview.

    Coordinates are in metres.  This model describes geometry only; it does
    not claim that the current automated gravity calculations analyse every
    member in this geometry.
    """

    x_spacings: Tuple[float, ...]
    y_spacings: Tuple[float, ...]
    columns: Tuple[Tuple[int, int], ...]

    @property
    def x_coords(self) -> Tuple[float, ...]:
        return self._coordinates(self.x_spacings)

    @property
    def y_coords(self) -> Tuple[float, ...]:
        return self._coordinates(self.y_spacings)

    @staticmethod
    def _coordinates(spacings: Tuple[float, ...]) -> Tuple[float, ...]:
        coords = [0.0]
        for spacing in spacings:
            coords.append(round(coords[-1] + spacing, 6))
        return tuple(coords)

    @property
    def beam_edges(self) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        selected = set(self.columns)
        edges = []
        for i, j in selected:
            for candidate in ((i + 1, j), (i, j + 1)):
                if candidate in selected:
                    edges.append(((i, j), candidate))
        return edges

    def to_dict(self) -> Dict:
        return {
            "x_spacings": list(self.x_spacings),
            "y_spacings": list(self.y_spacings),
            "columns": [list(c) for c in self.columns],
        }


def parse_spacings(text: str) -> Tuple[float, ...]:
    """Parse comma/space separated positive grid spacings."""
    raw = text.replace(";", ",").replace(" ", ",").split(",")
    values = []
    for item in raw:
        item = item.strip()
        if not item:
            continue
        value = float(item)
        if value <= 0:
            raise ValueError("Grid spacings must be greater than zero.")
        values.append(value)
    if not values:
        raise ValueError("Enter at least one grid spacing.")
    return tuple(values)
