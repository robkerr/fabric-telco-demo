"""Usage history: fact_usage_data (daily GB), fact_usage_voice (daily minutes)."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .common import GenContext, money


def generate(ctx: GenContext) -> None:
    acct = ctx.get("dim_account")
    active = acct[acct["status"].isin(["active", "suspended"])]["account_id"].to_numpy()
    days = int(ctx.config["usage_days"])
    dates = [(ctx.as_of - timedelta(days=d)).isoformat() for d in range(days, 0, -1)]

    n = len(active)
    # per-account daily mean profiles
    data_mean = ctx.rng.gamma(shape=3.0, scale=4.0, size=n)      # ~12 GB/day avg
    voice_mean = ctx.rng.gamma(shape=2.0, scale=8.0, size=n)     # ~16 min/day avg

    account_col = np.repeat(active, days)
    date_col = np.tile(dates, n)

    data_vals = ctx.rng.gamma(shape=2.0, scale=(np.repeat(data_mean, days) / 2.0))
    data_df = pd.DataFrame({
        "account_id": account_col,
        "usage_date": date_col,
        "gb_used": money(np.clip(data_vals, 0, None)),
    })
    ctx.add("fact_usage_data", data_df)

    voice_vals = ctx.rng.poisson(lam=np.clip(np.repeat(voice_mean, days), 0.1, None))
    voice_df = pd.DataFrame({
        "account_id": account_col,
        "usage_date": date_col,
        "minutes_used": voice_vals.astype(int),
    })
    ctx.add("fact_usage_voice", voice_df)
