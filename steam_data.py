"""Shared ownership-range definitions for all training and assessment notebooks.

These columns describe the outcome and must never be prediction inputs.
"""

import numpy as np
import pandas as pd

OWNER_LB = "Estimated owners (lb)"
OWNER_UB = "Estimated owners (ub)"
OWNER_MID = "Estimated owners (mid)"
OWNER_COLUMNS = [OWNER_LB, OWNER_UB, OWNER_MID]


def add_estimated_owner_columns(frame: pd.DataFrame, *, strict: bool = True) -> pd.DataFrame:
    """Parse 'lower - upper'; overwrite all three derived columns from the source.

    In non-strict cleaning mode, malformed/missing/reversed ranges have NaN in
    all three derived columns, so a caller can audit and exclude those records.
    Zero-width intervals, including '0 - 0', are valid intervals.
    """
    if "Estimated owners" not in frame:
        raise ValueError("Missing source column: Estimated owners")
    bounds = frame["Estimated owners"].astype("string").str.extract(
        r"^\s*(\d+)\s*-\s*(\d+)\s*$"
    ).apply(pd.to_numeric, errors="coerce").astype(float)
    valid = bounds.notna().all(axis=1) & np.isfinite(bounds).all(axis=1) & bounds[1].ge(bounds[0])
    if strict and not valid.all():
        raise ValueError(f"Invalid Estimated owners intervals in {int((~valid).sum())} rows")
    result = frame.copy()
    result[OWNER_LB] = bounds[0].where(valid)
    result[OWNER_UB] = bounds[1].where(valid)
    result[OWNER_MID] = (result[OWNER_LB] + result[OWNER_UB]) / 2
    return result


def ownership_target(frame: pd.DataFrame) -> pd.Series:
    """Deterministic classes: <20k, 20k–<100k, 100k+; reject ambiguous ranges."""
    if not set(OWNER_COLUMNS) <= set(frame):
        raise ValueError("Define ownership bounds and midpoint before constructing the target")
    lower, upper = frame[OWNER_LB], frame[OWNER_UB]
    if frame[OWNER_COLUMNS].isna().any().any() or (lower < 0).any() or (upper < lower).any():
        raise ValueError("Target requires valid ownership intervals")
    for edge in [20_000, 100_000]:
        if ((lower < edge) & (upper > edge)).any():
            raise ValueError(f"Ownership interval crosses {edge}; review target definition")
    return pd.Series(np.select([lower < 20_000, lower < 100_000], [0, 1], default=2),
                     index=frame.index, name="target", dtype="int64")
