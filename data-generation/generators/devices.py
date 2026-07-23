"""Customer devices: dim_customer_device (one physical device per internet subscription).

`dim_device` is a small *catalog* of device models (DEV_MODEM_STD, ...). This module creates a
distinct **physical device instance** per internet subscription so each account has its own
cable modem / router that real-time telemetry (DeviceMetrics in the Eventhouse) can attach to.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .common import GenContext, ids

# Device catalog models that represent a customer-premises internet device.
_CPE_TYPES = {"modem", "router"}
_FIRMWARE = ["3.4.1", "3.4.2", "3.5.0", "4.0.1", "4.1.0"]


def generate(ctx: GenContext) -> None:
    sub = ctx.get("fact_subscription")
    devices = ctx.get("dim_device").set_index("device_id")
    acct = ctx.get("dim_account").set_index("account_id")

    # Internet subscriptions whose device model is customer premises equipment (modem/router).
    cpe_models = {d for d in devices.index if str(devices.loc[d, "type"]) in _CPE_TYPES}
    internet = sub[(sub["product_id"] == "PROD_INT") & (sub["device_id"].isin(cpe_models))]

    rows = []
    for _, s in internet.iterrows():
        account_id = s["account_id"]
        model = s["device_id"]
        dev_type = str(devices.loc[model, "type"])
        status = str(acct.loc[account_id, "status"]) if account_id in acct.index else "active"
        customer_id = acct.loc[account_id, "customer_id"] if account_id in acct.index else None
        start = pd.to_datetime(s["start_date"]).date()
        # installed within ~10 days of the subscription start
        install = start + timedelta(days=int(ctx.rng.integers(0, 10)))
        install = min(install, ctx.as_of)
        rows.append({
            "device_id": None,
            "account_id": account_id,
            "customer_id": customer_id,
            "model": model,
            "model_name": str(devices.loc[model, "model"]),
            "device_type": dev_type,
            "serial_number": "SN" + format(int(ctx.rng.integers(0, 16**10)), "010X"),
            "install_date": install.isoformat(),
            "status": "active" if status in ("active", "suspended") else "inactive",
            "firmware_version": ctx.rng.choice(_FIRMWARE),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["device_id"] = ids("DVC", len(df))
    ctx.add("dim_customer_device", df)
