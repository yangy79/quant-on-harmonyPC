"""Pure-numpy drop-in replacement for qlib's Cython expanding._libs.

Same story as rolling.py: qlib ships expanding.pyx which cannot be compiled on
ohos_aarch64. This module provides expanding_mean / expanding_slope /
expanding_rsquare / expanding_resi in vectorized numpy.

Semantics from expanding.pyx:
  * each new value enters at physical position x = size (1-based), older values
    keep their index -> x == 1-based absolute index of the point;
  * NaN values are counted but contribute nothing to the sums;
  * slope/rsquare/resi use the same least-squares formulas as rolling with the
    window growing to the full series; resi predicts at the current (rightmost)
    point.

Regression on the absolute index is exactly equivalent (slope & R^2 are
translation-invariant; residual is evaluated at the current point).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _cum_sums(a):
    """Return expanding (N, Sx, Sx2, Sy, Sy2, Sxy) over valid points."""
    n = len(a)
    idx = np.arange(1, n + 1, dtype=np.float64)  # 1-based index == pyx "size"
    mask = ~np.isnan(a)
    m = mask.astype(np.float64)
    y = np.where(mask, a, 0.0)

    def cs(s):
        return pd.Series(s).cumsum().to_numpy()

    N = cs(m)
    Sx = cs(idx * m)
    Sx2 = cs(idx * idx * m)
    Sy = cs(y)
    Sy2 = cs(y * y)
    Sxy = cs(idx * y)
    return N, Sx, Sx2, Sy, Sy2, Sxy


def expanding_mean(a):
    a = np.asarray(a, dtype=np.float64)
    m = ~np.isnan(a)
    y = np.where(m, a, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = pd.Series(y).cumsum().to_numpy() / pd.Series(m.astype(float)).cumsum().to_numpy()
    return out


def expanding_slope(a):
    a = np.asarray(a, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        N, Sx, Sx2, Sy, Sy2, Sxy = _cum_sums(a)
        slope = (N * Sxy - Sx * Sy) / (N * Sx2 - Sx * Sx)
    return slope


def expanding_rsquare(a):
    a = np.asarray(a, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        N, Sx, Sx2, Sy, Sy2, Sxy = _cum_sums(a)
        num = N * Sxy - Sx * Sy
        r2 = (num * num) / ((N * Sx2 - Sx * Sx) * (N * Sy2 - Sy * Sy))
    return r2


def expanding_resi(a):
    a = np.asarray(a, dtype=np.float64)
    n = len(a)
    idx = np.arange(1, n + 1, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        N, Sx, Sx2, Sy, Sy2, Sxy = _cum_sums(a)
        slope = (N * Sxy - Sx * Sy) / (N * Sx2 - Sx * Sx)
        interp = (Sy - slope * Sx) / N
        resi = a - (slope * idx + interp)
    return resi
