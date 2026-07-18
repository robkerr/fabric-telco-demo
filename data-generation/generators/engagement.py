"""Engagement: fact_contact, fact_offer, fact_feedback."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .common import GenContext, ids, money

_CHANNELS = {"web": 0.30, "ivr": 0.20, "agent": 0.25, "chat": 0.25}
_REASONS = {
    "billing_question": 0.28, "technical_support": 0.24, "new_service": 0.14,
    "plan_change": 0.12, "outage_report": 0.10, "cancel_request": 0.06,
    "general_inquiry": 0.06,
}


def generate(ctx: GenContext) -> None:
    _contacts(ctx)
    _offers(ctx)
    _feedback(ctx)


def _contacts(ctx: GenContext) -> None:
    cust = ctx.get("dim_customer")
    lam = float(ctx.config["contacts_per_customer"])
    as_of_dt = datetime.combine(ctx.as_of, datetime.min.time())
    rows = []
    for customer_id in cust["customer_id"]:
        n = int(ctx.rng.poisson(lam))
        for _ in range(n):
            channel = ctx.rng.choice(list(_CHANNELS), p=list(_CHANNELS.values()))
            reason = ctx.rng.choice(list(_REASONS), p=list(_REASONS.values()))
            days_ago = int(ctx.rng.integers(0, 120))
            ts = as_of_dt - timedelta(days=days_ago, hours=int(ctx.rng.integers(0, 24)),
                                      minutes=int(ctx.rng.integers(0, 60)))
            # web/chat sessions sometimes hand off to a live agent
            handoff = bool(channel in ("web", "chat") and ctx.rng.random() < 0.25)
            rows.append({
                "contact_id": None,
                "customer_id": customer_id,
                "channel": channel,
                "reason": reason,
                "contact_ts": ts.isoformat(sep=" ", timespec="minutes"),
                "handoff_to_agent": handoff,
                "handled_by": ("agent" if channel == "agent" or handoff else "self-service"),
                "duration_min": int(np.clip(ctx.rng.normal(7, 4), 1, 45)),
            })
    df = pd.DataFrame(rows)
    df["contact_id"] = ids("CON", len(df))
    ctx.add("fact_contact", df)


def _offers(ctx: GenContext) -> None:
    acct = ctx.get("dim_account")
    promos = ctx.get("dim_promotion")
    subs = ctx.get("fact_subscription")
    rate = float(ctx.config["offer_rate"])

    # which accounts already have mobile (not cross-sell targets for mobile)
    has_mobile = set(subs[subs["product_id"] == "PROD_MOB"]["account_id"])

    acq = promos[promos["type"] == "acquisition"]["promotion_id"].tolist()
    xsell = promos[promos["type"] == "crosssell"]["promotion_id"].tolist()
    ret = promos[promos["type"] == "retention"]["promotion_id"].tolist()

    rows = []
    for _, a in acct.iterrows():
        if ctx.rng.random() >= rate:
            continue
        account_id = a["account_id"]
        if a["is_new_customer"]:
            pool = acq
        elif account_id not in has_mobile and ctx.rng.random() < 0.6:
            pool = xsell
        else:
            pool = ret
        promotion_id = ctx.rng.choice(pool)
        presented = ctx.as_of - timedelta(days=int(ctx.rng.integers(0, 90)))
        status = ctx.rng.choice(["offered", "accepted", "declined"], p=[0.5, 0.25, 0.25])
        rows.append({
            "offer_id": None,
            "account_id": account_id,
            "promotion_id": promotion_id,
            "presented_date": presented.isoformat(),
            "status": status,
            "channel": ctx.rng.choice(["agent", "web", "email", "sms"]),
        })
    df = pd.DataFrame(rows)
    df["offer_id"] = ids("OFR", len(df))
    ctx.add("fact_offer", df)


def _feedback(ctx: GenContext) -> None:
    acct = ctx.get("dim_account")
    rate = float(ctx.config["feedback_rate"])
    rows = []
    comments_pos = ["Great service", "Very helpful agent", "Quick resolution", "Happy with speed"]
    comments_neg = ["Long wait time", "Issue not resolved", "Bill was confusing", "Frequent outages"]
    comments_neu = ["It was okay", "Average experience", "No strong opinion"]
    for account_id in acct["account_id"]:
        if ctx.rng.random() >= rate:
            continue
        csat = int(ctx.rng.choice([1, 2, 3, 4, 5], p=[0.08, 0.10, 0.17, 0.35, 0.30]))
        nps = int(np.clip(csat * 2 + ctx.rng.integers(-2, 3), 0, 10))
        if csat >= 4:
            comment = ctx.rng.choice(comments_pos)
        elif csat <= 2:
            comment = ctx.rng.choice(comments_neg)
        else:
            comment = ctx.rng.choice(comments_neu)
        date_ = ctx.as_of - timedelta(days=int(ctx.rng.integers(0, 120)))
        rows.append({
            "feedback_id": None,
            "account_id": account_id,
            "csat": csat,
            "nps": nps,
            "comment": comment,
            "feedback_date": date_.isoformat(),
        })
    df = pd.DataFrame(rows)
    df["feedback_id"] = ids("FBK", len(df))
    ctx.add("fact_feedback", df)
