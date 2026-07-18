"""Shared context, RNG, and helpers for the synthetic telco data generators."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict

import numpy as np
import pandas as pd
from faker import Faker


@dataclass
class GenContext:
    """Carries config, RNG, the as-of date, and the growing set of generated frames."""

    config: dict
    seed: int
    as_of: date
    rng: np.random.Generator
    faker: Faker
    frames: Dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def n_customers(self) -> int:
        return int(self.config["customers"])

    def add(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        self.frames[name] = df
        return df

    def get(self, name: str) -> pd.DataFrame:
        return self.frames[name]


def make_context(config: dict) -> GenContext:
    seed = int(config["seed"])
    rng = np.random.default_rng(seed)
    faker = Faker("en_US")
    faker.seed_instance(seed)
    as_of = _parse_date(config["as_of_date"])
    return GenContext(config=config, seed=seed, as_of=as_of, rng=rng, faker=faker)


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


# ---------- helpers ----------

def choice(ctx: GenContext, options, size=None, p=None):
    return ctx.rng.choice(options, size=size, p=p)


def rand_dates(ctx: GenContext, start: date, end: date, size: int) -> np.ndarray:
    """Uniform random dates in [start, end]."""
    span = (end - start).days
    span = max(span, 1)
    offsets = ctx.rng.integers(0, span + 1, size=size)
    return np.array([start + timedelta(days=int(o)) for o in offsets], dtype="object")


def weighted_pick(ctx: GenContext, mapping: dict, size: int) -> np.ndarray:
    keys = list(mapping.keys())
    probs = np.array(list(mapping.values()), dtype=float)
    probs = probs / probs.sum()
    return ctx.rng.choice(keys, size=size, p=probs)


def money(values) -> np.ndarray:
    return np.round(np.asarray(values, dtype=float), 2)


def ids(prefix: str, n: int, start: int = 1) -> list[str]:
    width = max(6, len(str(start + n)))
    return [f"{prefix}{i:0{width}d}" for i in range(start, start + n)]
