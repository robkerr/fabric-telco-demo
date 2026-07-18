"""Customers + accounts: dim_customer, dim_account."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .common import GenContext, ids, weighted_pick

_SEGMENTS = {"Consumer": 0.75, "Premium": 0.15, "SmallBusiness": 0.10}
_CONTACT_PREF = {"email": 0.5, "sms": 0.3, "phone": 0.2}


def generate(ctx: GenContext) -> None:
    n = ctx.n_customers
    geo = ctx.get("dim_geography")
    geo_ids = geo["geo_id"].to_numpy()

    # Tenure: mixture of long-tenured and recent joins so first-bill journey has signal.
    tenure_months = np.clip(
        ctx.rng.gamma(shape=2.0, scale=14.0, size=n).astype(int), 0, 240)
    # Force a slice of brand-new customers (opened within new_customer_days).
    new_frac = 0.12
    n_new = int(n * new_frac)
    new_idx = ctx.rng.choice(n, size=n_new, replace=False)
    tenure_months[new_idx] = 0

    open_dates = []
    for i in range(n):
        if i in set(new_idx.tolist()):
            days_ago = int(ctx.rng.integers(1, ctx.config["new_customer_days"] + 1))
        else:
            days_ago = int(tenure_months[i] * 30 + ctx.rng.integers(0, 28))
        open_dates.append(ctx.as_of - timedelta(days=max(days_ago, 1)))

    first_names = [ctx.faker.first_name() for _ in range(n)]
    last_names = [ctx.faker.last_name() for _ in range(n)]

    cust = pd.DataFrame({
        "customer_id": ids("CUST", n),
        "first_name": first_names,
        "last_name": last_names,
        "email": [f"{f}.{l}{ctx.rng.integers(1, 999)}@example.com".lower()
                  for f, l in zip(first_names, last_names)],
        "phone": [ctx.faker.numerify("###-###-####") for _ in range(n)],
        "date_of_birth": [ctx.faker.date_of_birth(minimum_age=18, maximum_age=85).isoformat()
                          for _ in range(n)],
        "segment": weighted_pick(ctx, _SEGMENTS, n),
        "geo_id": ctx.rng.choice(geo_ids, size=n),
        "tenure_months": tenure_months,
        "contact_pref": weighted_pick(ctx, _CONTACT_PREF, n),
        "marketing_opt_in": ctx.rng.choice([True, False], size=n, p=[0.6, 0.4]),
    })
    ctx.add("dim_customer", cust)

    # One account per customer (keeps the demo simple).
    status = weighted_pick(ctx, ctx.config["account_status"], n)
    open_dates_iso = [d.isoformat() for d in open_dates]
    new_customer_flag = [(ctx.as_of - d).days <= ctx.config["new_customer_days"]
                         for d in open_dates]

    acct = pd.DataFrame({
        "account_id": ids("ACCT", n),
        "customer_id": cust["customer_id"].to_numpy(),
        "status": status,
        "open_date": open_dates_iso,
        "autopay": ctx.rng.choice([True, False], size=n, p=[0.55, 0.45]),
        "paperless_billing": ctx.rng.choice([True, False], size=n, p=[0.7, 0.3]),
        "credit_class": weighted_pick(ctx, {"A": 0.5, "B": 0.3, "C": 0.2}, n),
        "is_new_customer": new_customer_flag,
    })
    # cancelled accounts get a close date; others null.
    close = []
    for st, od in zip(status, open_dates):
        if st == "cancelled":
            close.append((od + timedelta(days=int(ctx.rng.integers(60, 720)))).isoformat())
        else:
            close.append(None)
    acct["close_date"] = close
    ctx.add("dim_account", acct)
