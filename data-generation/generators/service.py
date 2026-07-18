"""Service performance & operations: outages, service metrics, work orders, appointments."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .common import GenContext, ids, money

_SEVERITY = {"Minor": 0.5, "Major": 0.35, "Critical": 0.15}
_WO_TYPES = {"Repair": 0.45, "Install": 0.30, "Upgrade": 0.15, "Disconnect": 0.10}


def generate(ctx: GenContext) -> None:
    geo = ctx.get("dim_geography")
    acct = ctx.get("dim_account")
    cust = ctx.get("dim_customer").set_index("customer_id")

    _outages(ctx, geo)
    _service_metrics(ctx, acct, cust)
    _work_orders(ctx, acct)


def _outages(ctx: GenContext, geo: pd.DataFrame) -> None:
    n = int(ctx.config["outage_count"])
    geo_ids = geo["geo_id"].to_numpy()
    rows = []
    metric_window = int(ctx.config["service_metric_days"])
    for i in range(n):
        gid = ctx.rng.choice(geo_ids)
        # bias ~40% of outages into the recent service-metric window for demo signal
        if ctx.rng.random() < 0.4:
            days_ago = int(ctx.rng.integers(0, metric_window))
        else:
            days_ago = int(ctx.rng.integers(metric_window, 180))
        as_of_dt = datetime.combine(ctx.as_of, datetime.min.time())
        start = as_of_dt - timedelta(days=days_ago,
                                     hours=int(ctx.rng.integers(0, 24)))
        dur_hours = float(ctx.rng.gamma(shape=2.0, scale=3.0))
        end = start + timedelta(hours=dur_hours)
        # Resolved if it ended before "now"; a few very recent ones remain ongoing.
        resolved = bool(end <= as_of_dt and ctx.rng.random() < 0.95)
        rows.append({
            "outage_id": None,
            "geo_id": gid,
            "start_time": start.isoformat(sep=" ", timespec="minutes"),
            "end_time": end.isoformat(sep=" ", timespec="minutes") if resolved else None,
            "severity": ctx.rng.choice(list(_SEVERITY), p=list(_SEVERITY.values())),
            "duration_hours": money(dur_hours),
            "resolved": bool(resolved),
            "root_cause": ctx.rng.choice(
                ["Fiber cut", "Power loss", "Equipment failure", "Weather", "Congestion"]),
        })
    df = pd.DataFrame(rows)
    df["outage_id"] = ids("OUT", len(df))
    ctx.add("fact_outage", df)


def _service_metrics(ctx: GenContext, acct: pd.DataFrame, cust: pd.DataFrame) -> None:
    outages = ctx.get("fact_outage")
    window = int(ctx.config["service_metric_days"])
    # geos with a recent outage in the window
    recent_geos = set()
    for _, o in outages.iterrows():
        start = pd.to_datetime(o["start_time"]).date()
        if (ctx.as_of - start).days <= window:
            recent_geos.add(o["geo_id"])

    active = acct[acct["status"].isin(["active", "suspended"])].copy()
    active["geo_id"] = active["customer_id"].map(cust["geo_id"])
    active["degraded"] = active["geo_id"].isin(recent_geos)

    account_ids = active["account_id"].to_numpy()
    degraded = active["degraded"].to_numpy()
    dates = [(ctx.as_of - timedelta(days=d)).isoformat() for d in range(window, 0, -1)]

    rows_acct = np.repeat(account_ids, window)
    rows_deg = np.repeat(degraded, window)
    rows_date = np.tile(dates, len(account_ids))
    m = len(rows_acct)

    latency = np.where(rows_deg,
                       ctx.rng.uniform(60, 180, size=m),
                       ctx.rng.uniform(10, 45, size=m))
    packet_loss = np.where(rows_deg,
                           ctx.rng.uniform(1.0, 6.0, size=m),
                           ctx.rng.uniform(0.0, 0.6, size=m))
    uptime = np.where(rows_deg,
                      ctx.rng.uniform(93.0, 99.0, size=m),
                      ctx.rng.uniform(99.5, 100.0, size=m))

    sm = pd.DataFrame({
        "account_id": rows_acct,
        "metric_date": rows_date,
        "latency_ms": money(latency),
        "packet_loss_pct": money(packet_loss),
        "uptime_pct": money(uptime),
    })
    ctx.add("fact_service_metric", sm)


def _work_orders(ctx: GenContext, acct: pd.DataFrame) -> None:
    rate = float(ctx.config["work_order_rate"])
    wo_rows = []
    appt_rows = []
    for _, a in acct.iterrows():
        if ctx.rng.random() >= rate:
            continue
        n_wo = int(ctx.rng.integers(1, 3))
        open_date = pd.to_datetime(a["open_date"]).date()
        for _ in range(n_wo):
            wtype = ctx.rng.choice(list(_WO_TYPES), p=list(_WO_TYPES.values()))
            opened = open_date + timedelta(days=int(ctx.rng.integers(0, max(
                1, (ctx.as_of - open_date).days))))
            opened = min(opened, ctx.as_of)
            is_open = ctx.rng.random() < 0.2
            closed = None if is_open else (opened + timedelta(
                days=int(ctx.rng.integers(0, 10)))).isoformat()
            wo_id = f"WO{len(wo_rows) + 1:07d}"
            wo_rows.append({
                "work_order_id": wo_id,
                "account_id": a["account_id"],
                "type": wtype,
                "opened_date": opened.isoformat(),
                "closed_date": closed,
                "status": "open" if is_open else "closed",
                "priority": ctx.rng.choice(["Low", "Medium", "High"], p=[0.5, 0.35, 0.15]),
                "resolution": None if is_open else ctx.rng.choice(
                    ["Resolved remotely", "Truck roll - fixed", "Replaced equipment",
                     "Customer educated"]),
            })
            # ~55% of work orders have an on-site appointment
            if ctx.rng.random() < 0.55:
                win_start = opened + timedelta(days=int(ctx.rng.integers(1, 7)))
                appt_rows.append({
                    "appointment_id": f"APPT{len(appt_rows) + 1:07d}",
                    "work_order_id": wo_id,
                    "window_start": f"{win_start.isoformat()} 08:00",
                    "window_end": f"{win_start.isoformat()} 12:00",
                    "status": ctx.rng.choice(["scheduled", "completed", "missed"],
                                             p=[0.25, 0.65, 0.10]),
                    "technician": ctx.faker.name(),
                })
    ctx.add("fact_work_order", pd.DataFrame(wo_rows))
    ctx.add("fact_appointment", pd.DataFrame(appt_rows))
