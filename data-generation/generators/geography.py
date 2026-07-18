"""Geography + coverage: dim_geography, fact_coverage."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import GenContext, ids, money

# A compact set of US metro seeds (city, state, region). ZIPs are synthesized.
_METROS = [
    ("Seattle", "WA", "West"), ("Portland", "OR", "West"), ("San Jose", "CA", "West"),
    ("Denver", "CO", "West"), ("Phoenix", "AZ", "West"), ("Austin", "TX", "South"),
    ("Dallas", "TX", "South"), ("Houston", "TX", "South"), ("Atlanta", "GA", "South"),
    ("Miami", "FL", "South"), ("Charlotte", "NC", "South"), ("Nashville", "TN", "South"),
    ("Chicago", "IL", "Midwest"), ("Minneapolis", "MN", "Midwest"), ("Columbus", "OH", "Midwest"),
    ("Detroit", "MI", "Midwest"), ("Kansas City", "MO", "Midwest"), ("Boston", "MA", "Northeast"),
    ("New York", "NY", "Northeast"), ("Philadelphia", "PA", "Northeast"), ("Pittsburgh", "PA", "Northeast"),
]

_TECHS = ["Fiber", "Cable", "DSL", "FixedWireless"]
_TECH_SPEEDS = {
    "Fiber": (1000, 5000),
    "Cable": (200, 1200),
    "DSL": (25, 100),
    "FixedWireless": (50, 300),
}


def generate(ctx: GenContext) -> None:
    n = int(ctx.config["geo_count"])
    metro_idx = ctx.rng.integers(0, len(_METROS), size=n)
    cities = [_METROS[i][0] for i in metro_idx]
    states = [_METROS[i][1] for i in metro_idx]
    regions = [_METROS[i][2] for i in metro_idx]
    zips = [f"{ctx.rng.integers(10000, 99999):05d}" for _ in range(n)]

    geo = pd.DataFrame({
        "geo_id": ids("GEO", n),
        "zip": zips,
        "city": cities,
        "state": states,
        "region": regions,
        "latitude": money(ctx.rng.uniform(25.0, 48.0, size=n)),
        "longitude": money(ctx.rng.uniform(-124.0, -68.0, size=n)),
        "urban_flag": ctx.rng.choice([True, False], size=n, p=[0.7, 0.3]),
    })
    ctx.add("dim_geography", geo)

    # Coverage: each geo has 1-3 technologies available with max speeds.
    rows = []
    for gid, urban in zip(geo["geo_id"], geo["urban_flag"]):
        # urban areas more likely to have fiber/cable
        if urban:
            techs = ctx.rng.choice(_TECHS, size=ctx.rng.integers(2, 4), replace=False,
                                   p=[0.4, 0.35, 0.15, 0.10])
        else:
            techs = ctx.rng.choice(_TECHS, size=ctx.rng.integers(1, 3), replace=False,
                                   p=[0.15, 0.30, 0.30, 0.25])
        for t in set(techs.tolist()):
            lo, hi = _TECH_SPEEDS[t]
            down = int(ctx.rng.integers(lo, hi + 1))
            up = int(max(10, down * ctx.rng.uniform(0.1, 0.5)))
            rows.append((gid, t, down, up))
    cov = pd.DataFrame(rows, columns=["geo_id", "technology", "max_down_mbps", "max_up_mbps"])
    cov.insert(0, "coverage_id", ids("COV", len(cov)))
    ctx.add("fact_coverage", cov)
