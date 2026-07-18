"""
Customer 360 data access for the agent-desktop web app.

Two modes:
  1. LIVE  - query customer_360 on the Fabric SQL analytics endpoint (the production path).
  2. LOCAL - build a profile from the committed sample data in ../data/csv (demo without cloud).

Mode is chosen automatically: LIVE if FABRIC_SQL_ENDPOINT + FABRIC_LAKEHOUSE_NAME are set
and pyodbc + a token are available; otherwise LOCAL.
"""
from __future__ import annotations

import os
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
CSV_DIR = REPO / "data" / "csv"

SQL_COPT_SS_ACCESS_TOKEN = 1256  # pyodbc access-token attribute


def _sql_endpoint() -> Optional[str]:
    return os.environ.get("FABRIC_SQL_ENDPOINT")


def mode() -> str:
    if _sql_endpoint() and os.environ.get("FABRIC_LAKEHOUSE_NAME"):
        try:
            import pyodbc  # noqa: F401
            return "live"
        except Exception:  # noqa: BLE001
            return "local"
    return "local"


# ---------------- LIVE (Fabric SQL endpoint) ----------------

def _access_token_struct() -> bytes:
    from azure.identity import DefaultAzureCredential
    token = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
    b = token.encode("utf-16-le")
    return struct.pack("=i", len(b)) + b


def _live_profile(customer_id: str) -> Optional[dict[str, Any]]:
    import pyodbc
    server = _sql_endpoint()
    database = os.environ["FABRIC_LAKEHOUSE_NAME"]
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={server};Database={database};Encrypt=yes;TrustServerCertificate=no;"
    )
    token = _access_token_struct()
    with pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token}) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM gold.customer_360 WHERE customer_id = ?", customer_id)
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return {c: _json_safe(v) for c, v in zip(cols, row)}


def _live_search(query: str, limit: int) -> list[dict[str, Any]]:
    import pyodbc
    server = _sql_endpoint()
    database = os.environ["FABRIC_LAKEHOUSE_NAME"]
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={server};Database={database};Encrypt=yes;TrustServerCertificate=no;"
    )
    token = _access_token_struct()
    like = f"%{query}%"
    with pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token}) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP (?) customer_id, first_name, last_name, city, state, account_status "
            "FROM gold.customer_360 WHERE customer_id LIKE ? OR last_name LIKE ? OR first_name LIKE ?",
            limit, like, like, like)
        cols = [d[0] for d in cur.description]
        return [{c: _json_safe(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


# ---------------- LOCAL (sample data) ----------------

@lru_cache(maxsize=1)
def _local_360():
    import pandas as pd

    def rd(name):
        return pd.read_csv(CSV_DIR / f"{name}.csv")

    c, a, g = rd("dim_customer"), rd("dim_account"), rd("dim_geography")
    sub = rd("fact_subscription")
    inv = rd("fact_invoice")
    ch = rd("ml_churn_score")
    xs = rd("ml_crosssell_reco")

    sub_a = sub[sub.status == "active"].groupby("account_id").agg(
        active_products=("product_id", "size"), total_mrc=("mrc", "sum"),
        product_list=("product_id", lambda s: ", ".join(s))).reset_index()
    latest = inv.sort_values("period_end").groupby("account_id").tail(1)[
        ["account_id", "amount", "due_date", "paid", "is_first_bill"]].rename(
        columns={"amount": "last_invoice_amount", "due_date": "last_invoice_due",
                 "paid": "last_invoice_paid", "is_first_bill": "last_invoice_is_first_bill"})
    bal = inv[~inv.paid].groupby("account_id")["amount"].sum().reset_index().rename(
        columns={"amount": "open_balance"})

    df = (c.merge(a, on="customer_id").merge(g, on="geo_id", how="left")
          .merge(sub_a, on="account_id", how="left")
          .merge(latest, on="account_id", how="left")
          .merge(bal, on="account_id", how="left")
          .merge(ch[["customer_id", "churn_probability", "risk_band", "top_reason"]],
                 on="customer_id", how="left")
          .merge(xs[["account_id", "recommended_product_id", "score"]], on="account_id", how="left"))
    df = df.rename(columns={"status": "account_status", "top_reason": "churn_top_reason",
                            "recommended_product_id": "top_crosssell_product",
                            "score": "top_crosssell_score"})
    return df.fillna("")


def _local_profile(customer_id: str) -> Optional[dict[str, Any]]:
    df = _local_360()
    hit = df[df.customer_id == customer_id]
    if hit.empty:
        return None
    return {k: _json_safe(v) for k, v in hit.iloc[0].to_dict().items()}


def _local_search(query: str, limit: int) -> list[dict[str, Any]]:
    df = _local_360()
    q = query.lower()
    mask = (df.customer_id.str.lower().str.contains(q)
            | df.last_name.str.lower().str.contains(q)
            | df.first_name.str.lower().str.contains(q))
    cols = ["customer_id", "first_name", "last_name", "city", "state", "account_status"]
    return df[mask][cols].head(limit).to_dict("records")


# ---------------- public API ----------------

def get_profile(customer_id: str) -> Optional[dict[str, Any]]:
    return _live_profile(customer_id) if mode() == "live" else _local_profile(customer_id)


def search_customers(query: str, limit: int = 10) -> list[dict[str, Any]]:
    return _live_search(query, limit) if mode() == "live" else _local_search(query, limit)


def _json_safe(v):
    import datetime
    import math
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, float) and math.isnan(v):
        return ""
    return v
