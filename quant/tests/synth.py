"""Deterministic synthetic OHLCV data for tests. Not market data; never used for results."""

import numpy as np
import pandas as pd


def random_walk_ohlcv(n: int = 1500, seed: int = 7, vol: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, vol, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    spread = np.abs(rng.normal(0.0, vol * 0.3, n))
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) * (1 + spread),
            "low": np.minimum(open_, close) * (1 - spread),
            "close": close,
            "volume": rng.lognormal(mean=5.0, sigma=0.5, size=n),
        }
    )
