"""Rule-based synthetic ML outputs: ml_churn_score, ml_crosssell_reco.

These are deterministic heuristics (not a trained model) so the demo is self-contained
and reproducible. They still produce believable signal aligned to the other tables.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import GenContext, ids, money


def generate(ctx: GenContext) -> None:
    _churn(ctx)
    _crosssell(ctx)


def _churn(ctx: GenContext) -> None:
    acct = ctx.get("dim_account")
    cust = ctx.get("dim_customer").set_index("customer_id")
    invoices = ctx.get("fact_invoice")
    feedback = ctx.get("fact_feedback")
    metrics = ctx.get("fact_service_metric")
    contacts = ctx.get("fact_contact")

    # feature aggregates
    unpaid = invoices[~invoices["paid"]].groupby("account_id").size()
    avg_uptime = metrics.groupby("account_id")["uptime_pct"].mean()
    avg_csat = feedback.groupby("account_id")["csat"].mean()
    cancel_contacts = contacts[contacts["reason"] == "cancel_request"].groupby("customer_id").size()

    rows = []
    for _, a in acct.iterrows():
        account_id = a["account_id"]
        customer_id = a["customer_id"]
        tenure = float(cust.loc[customer_id, "tenure_months"])

        score = 0.10
        reasons = []
        if a["status"] == "suspended":
            score += 0.25; reasons.append("account suspended")
        if account_id in unpaid.index and unpaid[account_id] > 0:
            score += 0.10 * min(int(unpaid[account_id]), 3); reasons.append("unpaid invoices")
        up = avg_uptime.get(account_id, 100.0)
        if up < 99.0:
            score += 0.20; reasons.append("degraded service")
        cs = avg_csat.get(account_id, 5.0)
        if cs <= 2.5:
            score += 0.20; reasons.append("low satisfaction")
        if customer_id in cancel_contacts.index:
            score += 0.25; reasons.append("cancellation intent")
        if tenure < 6:
            score += 0.10; reasons.append("new/short tenure")
        elif tenure > 48:
            score -= 0.05
        if not a["autopay"]:
            score += 0.05

        # small deterministic jitter from the seeded RNG
        score += ctx.rng.uniform(-0.03, 0.03)
        prob = float(np.clip(score, 0.01, 0.98))
        band = "High" if prob >= 0.55 else ("Medium" if prob >= 0.30 else "Low")
        top_reason = reasons[0] if reasons else "stable account"

        rows.append({
            "customer_id": customer_id,
            "account_id": account_id,
            "churn_probability": round(prob, 3),
            "risk_band": band,
            "top_reason": top_reason,
            "scored_date": ctx.as_of.isoformat(),
        })
    ctx.add("ml_churn_score", pd.DataFrame(rows))


def _crosssell(ctx: GenContext) -> None:
    acct = ctx.get("dim_account")
    cust = ctx.get("dim_customer").set_index("customer_id")
    subs = ctx.get("fact_subscription")

    prod_by_acct = subs.groupby("account_id")["product_id"].agg(set).to_dict()

    rows = []
    for _, a in acct.iterrows():
        if a["status"] == "cancelled":
            continue
        account_id = a["account_id"]
        owned = prod_by_acct.get(account_id, set())
        tenure = float(cust.loc[a["customer_id"], "tenure_months"])

        candidates = []
        if "PROD_MOB" not in owned:
            candidates.append(("PROD_MOB", "PROMO_XSELL_1",
                               "Internet customer without mobile"))
        if "PROD_TV" not in owned:
            candidates.append(("PROD_TV", "PROMO_XSELL_2",
                               "Eligible for TV + internet bundle"))
        if "PROD_VOICE" not in owned and ctx.rng.random() < 0.4:
            candidates.append(("PROD_VOICE", None, "Add home phone to bundle"))
        if not candidates:
            continue
        # pick the top candidate deterministically-ish
        rec = candidates[0]
        base = 0.4 + min(tenure, 60) / 200.0
        score = float(np.clip(base + ctx.rng.uniform(-0.1, 0.2), 0.05, 0.98))
        rows.append({
            "account_id": account_id,
            "recommended_product_id": rec[0],
            "recommended_promotion_id": rec[1],
            "score": round(score, 3),
            "rationale": rec[2],
            "scored_date": ctx.as_of.isoformat(),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df.insert(0, "reco_id", ids("REC", len(df)))
    ctx.add("ml_crosssell_reco", df)
