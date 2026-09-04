"""Pure-numpy drop-in replacement for qlib's Cython rolling._libs.

HarmonyOS/ohos_aarch64 cannot compile the Cython extensions shipped with qlib
(qlib/data/_libs/rolling.pyx). This module re-implements the SAME public API
(rolling_mean / rolling_slope / rolling_rsquare / rolling_resi) in vectorized
numpy so that ``import qlib.data._libs.rolling`` succeeds without compilation.

Semantics replicated from rolling.pyx:
  * an internal deque of `window` slots is pre-filled with NaN (right-aligned);
  * each new value enters at physical position x = window, older values shift
    left by one on every update;
  * NaN values occupy a slot but do not contribute to the sums;
  * x = physical position within the window (1..window), y = value;
  * slope    = (N*Sxy - Sx*Sy) / (N*Sx2 - Sx^2)
  * rsquare  = slope numerator^2 / ((N*Sx2-Sx^2) * (N*Sy2-Sy^2))
  * resi     = val - (slope*window + interp)   (prediction at right edge)

Because a linear-regression slope & R^2 are invariant under shifting x by a
constant, we may regress y on the ABSOLUTE index i (0..n-1) and obtain the
same slope / rsquare as the pyx code; the residual is also identical since
predicting at x=window is just the absolute-index fit evaluated at the current
point. Rolling sums are computed with pandas for exact NaN handling.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _roll_sums(a, window):
    """Return rolling (N, Sx, Sx2, Sy, Sy2, Sxy) over valid (non-NaN) points."""
    n = len(a)
    idx = np.arange(n, dtype=np.float64)
    mask = ~np.isnan(a)
    m = mask.astype(np.float64)
    y = np.where(mask, a, 0.0)

    def rs(s):
        return pd.Series(s).rolling(window, min_periods=1).sum().to_numpy()

    N = rs(m)
    Sx = rs(idx * m)
    Sx2 = rs(idx * idx * m)
    Sy = rs(y)
    Sy2 = rs(y * y)
    Sxy = rs(idx * y)
    return N, Sx, Sx2, Sy, Sy2, Sxy


def rolling_mean(a, window):
    a = np.asarray(a, dtype=np.float64)
    out = np.full(len(a), np.nan)
    m = ~np.isnan(a)
    y = np.where(m, a, 0.0)
    N = pd.Series(m.astype(float)).rolling(window, min_periods=1).sum().to_numpy()
    S = pd.Series(y).rolling(window, min_periods=1).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        out = S / N
    return out


def rolling_slope(a, window):
    a = np.asarray(a, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        N, Sx, Sx2, Sy, Sy2, Sxy = _roll_sums(a, window)
        denom = N * Sx2 - Sx * Sx
        slope = (N * Sxy - Sx * Sy) / denom
    return slope


def rolling_rsquare(a, window):
    a = np.asarray(a, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        N, Sx, Sx2, Sy, Sy2, Sxy = _roll_sums(a, window)
        denom_x = N * Sx2 - Sx * Sx
        denom_y = N * Sy2 - Sy * Sy
        num = N * Sxy - Sx * Sy
        r2 = (num * num) / (denom_x * denom_y)
    return r2


def rolling_resi(a, window):
    a = np.asarray(a, dtype=np.float64)
    n = len(a)
    idx = np.arange(n, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        N, Sx, Sx2, Sy, Sy2, Sxy = _roll_sums(a, window)
        denom = N * Sx2 - Sx * Sx
        slope = (N * Sxy - Sx * Sy) / denom
        interp = (Sy - slope * Sx) / N
        # residual of the CURRENT point relative to the fit evaluated at its x
        resi = a - (slope * idx + interp)
    return resi
