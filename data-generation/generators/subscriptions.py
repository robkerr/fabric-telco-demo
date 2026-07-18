"""Subscriptions: fact_subscription (customer product instances)."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .common import GenContext, ids, money

_INT_PLANS = ["PLAN_INT_100", "PLAN_INT_500", "PLAN_INT_1G", "PLAN_INT_2G"]
_INT_PLAN_P = [0.30, 0.35, 0.25, 0.10]
_MOB_PLANS = ["PLAN_MOB_UNL", "PLAN_MOB_40", "PLAN_MOB_10"]
_MOB_PLAN_P = [0.5, 0.3, 0.2]


def generate(ctx: GenContext) -> None:
    acct = ctx.get("dim_account")
    plans = ctx.get("dim_plan").set_index("plan_id")
    devices = ctx.get("dim_device").set_index("device_id")

    rows = []
    multi_rate = float(ctx.config["multi_product_rate"])

    for account_id, open_date_iso, status in zip(
            acct["account_id"], acct["open_date"], acct["status"]):
        open_date = pd.to_datetime(open_date_iso).date()
        end_date = None
        if status == "cancelled":
            end_date = (open_date + timedelta(days=int(ctx.rng.integers(90, 700)))).isoformat()

        # Primary: internet
        plan_id = ctx.rng.choice(_INT_PLANS, p=_INT_PLAN_P)
        device_id = ctx.rng.choice(["DEV_MODEM_STD", "DEV_ROUTER_MESH"], p=[0.6, 0.4])
        rows.append(_sub_row(ctx, account_id, "PROD_INT", plan_id, device_id,
                             open_date, end_date, plans, devices))

        # Additional products (cross-sell candidates are those WITHOUT these).
        if ctx.rng.random() < multi_rate:
            mob_plan = ctx.rng.choice(_MOB_PLANS, p=_MOB_PLAN_P)
            phone = ctx.rng.choice(["DEV_PHONE_A", "DEV_PHONE_B", "DEV_NONE"], p=[0.4, 0.3, 0.3])
            add_date = open_date + timedelta(days=int(ctx.rng.integers(0, 400)))
            rows.append(_sub_row(ctx, account_id, "PROD_MOB", mob_plan, phone,
                                 min(add_date, ctx.as_of), end_date, plans, devices))
        if ctx.rng.random() < multi_rate * 0.4:
            add_date = open_date + timedelta(days=int(ctx.rng.integers(0, 400)))
            rows.append(_sub_row(ctx, account_id, "PROD_TV", "PLAN_TV_STD", "DEV_NONE",
                                 min(add_date, ctx.as_of), end_date, plans, devices))
        if ctx.rng.random() < multi_rate * 0.25:
            add_date = open_date + timedelta(days=int(ctx.rng.integers(0, 400)))
            rows.append(_sub_row(ctx, account_id, "PROD_VOICE", "PLAN_VOICE_STD", "DEV_NONE",
                                 min(add_date, ctx.as_of), end_date, plans, devices))

    sub = pd.DataFrame(rows)
    sub.insert(0, "subscription_id", ids("SUB", len(sub)))
    ctx.add("fact_subscription", sub)


def _sub_row(ctx, account_id, product_id, plan_id, device_id, start_date, end_date, plans, devices):
    plan_price = float(plans.loc[plan_id, "price"])
    dev_price = float(devices.loc[device_id, "monthly_price"])
    return {
        "account_id": account_id,
        "product_id": product_id,
        "plan_id": plan_id,
        "device_id": device_id,
        "start_date": start_date.isoformat() if hasattr(start_date, "isoformat") else start_date,
        "end_date": end_date,
        "status": "active" if end_date is None else "cancelled",
        "mrc": money(plan_price + dev_price),
    }
