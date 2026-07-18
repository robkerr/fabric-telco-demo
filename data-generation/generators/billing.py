"""Billing: fact_invoice, fact_invoice_line. First invoice flagged is_first_bill."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .common import GenContext, money


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, 28))


def generate(ctx: GenContext) -> None:
    acct = ctx.get("dim_account")
    subs = ctx.get("fact_subscription")
    max_months = int(ctx.config["max_billing_months"])

    subs_by_acct = {aid: g for aid, g in subs.groupby("account_id")}

    inv_rows = []
    line_rows = []
    inv_seq = 0
    line_seq = 0

    for _, a in acct.iterrows():
        account_id = a["account_id"]
        open_date = pd.to_datetime(a["open_date"]).date()
        status = a["status"]
        acct_subs = subs_by_acct.get(account_id)
        if acct_subs is None:
            continue

        # number of monthly bills issued so far
        months_elapsed = 0
        cur = _add_months(open_date, 1)
        while cur <= ctx.as_of and months_elapsed < max_months:
            months_elapsed += 1
            cur = _add_months(open_date, months_elapsed + 1)
        if months_elapsed == 0:
            # brand-new account, first bill not yet issued -> still create a pending first bill
            months_elapsed = 1

        for m in range(months_elapsed):
            period_start = _add_months(open_date, m)
            period_end = _add_months(open_date, m + 1) - timedelta(days=1)
            is_first = (m == 0)

            inv_seq += 1
            invoice_id = f"INV{inv_seq:07d}"

            # recurring lines from subscriptions active by period_start
            amount = 0.0
            for _, s in acct_subs.iterrows():
                s_start = pd.to_datetime(s["start_date"]).date()
                if s_start <= period_end:
                    line_seq += 1
                    line_rows.append({
                        "invoice_line_id": f"INL{line_seq:08d}",
                        "invoice_id": invoice_id,
                        "description": f"{s['product_id']} monthly service",
                        "category": "recurring",
                        "amount": money(s["mrc"]),
                    })
                    amount += float(s["mrc"])

            # first bill: activation fee + partial proration (makes first bill higher/confusing)
            if is_first:
                line_seq += 1
                activation = 35.00
                line_rows.append({
                    "invoice_line_id": f"INL{line_seq:08d}",
                    "invoice_id": invoice_id,
                    "description": "One-time activation fee",
                    "category": "one-time",
                    "amount": money(activation),
                })
                amount += activation
                proration = round(amount * ctx.rng.uniform(0.1, 0.4), 2)
                line_seq += 1
                line_rows.append({
                    "invoice_line_id": f"INL{line_seq:08d}",
                    "invoice_id": invoice_id,
                    "description": "Partial month proration",
                    "category": "one-time",
                    "amount": money(proration),
                })
                amount += proration

            # occasional usage overage
            if ctx.rng.random() < 0.12:
                overage = round(ctx.rng.uniform(5, 40), 2)
                line_seq += 1
                line_rows.append({
                    "invoice_line_id": f"INL{line_seq:08d}",
                    "invoice_id": invoice_id,
                    "description": "Data usage overage",
                    "category": "usage",
                    "amount": money(overage),
                })
                amount += overage

            # occasional credit
            if ctx.rng.random() < 0.08:
                credit = -round(ctx.rng.uniform(5, 30), 2)
                line_seq += 1
                line_rows.append({
                    "invoice_line_id": f"INL{line_seq:08d}",
                    "invoice_id": invoice_id,
                    "description": "Goodwill/service credit",
                    "category": "credit",
                    "amount": money(credit),
                })
                amount += credit

            due_date = period_end + timedelta(days=20)
            is_latest = (m == months_elapsed - 1)
            # payment logic
            if status == "cancelled":
                paid = ctx.rng.random() < 0.7
            elif status == "suspended":
                paid = not is_latest and ctx.rng.random() < 0.5
            else:
                paid = (not is_latest) or (ctx.rng.random() < 0.6)
            # brand-new first bill is typically still open
            if is_first and is_latest and a["is_new_customer"]:
                paid = False

            inv_rows.append({
                "invoice_id": invoice_id,
                "account_id": account_id,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "due_date": due_date.isoformat(),
                "amount": money(amount),
                "paid": bool(paid),
                "paid_date": (due_date - timedelta(days=int(ctx.rng.integers(0, 18)))).isoformat()
                             if paid else None,
                "is_first_bill": bool(is_first),
            })

    ctx.add("fact_invoice", pd.DataFrame(inv_rows))
    ctx.add("fact_invoice_line", pd.DataFrame(line_rows))
