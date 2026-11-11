"""Small helpers for safely persisting calculation state to JSON.

The calculation modules use NumPy scalars internally (the slope-deflection
solver returns ``numpy.float64``). ``json.dumps(..., default=str)`` converts
those to *strings*, so a saved project could reload with
``"M_span_kNm": "79.05"`` and break any later arithmetic in the UI. This
module converts numeric NumPy types to native Python numbers before saving.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return value.item()
        except (ValueError, AttributeError):
            return value
    return value
