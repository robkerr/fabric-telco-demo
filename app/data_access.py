"""
Customer 360 data access for the agent-desktop web app.

Data access is abstracted behind a small DataProvider interface so the app can pivot
from local sample CSVs to the Fabric Lakehouse gold tables with *no* changes to main.py
or the UI. Two providers implement the same surface:

  - LocalCsvProvider  : builds views from the committed sample CSVs (data/csv). Demo w/o cloud.
  - FabricSqlProvider : queries the gold.* tables on the Fabric SQL analytics endpoint.

The active provider is chosen by mode():
  'live'  when FABRIC_SQL_ENDPOINT + FABRIC_LAKEHOUSE_NAME are set and pyodbc is importable
  'local' otherwise.

To pivot to Fabric, set those env vars (and install ODBC Driver 18) — nothing else changes.
The column lists in COLS are the single source of truth shared by both providers, so the
shape returned to the UI is identical regardless of source.
"""
from __future__ import annotations

import datetime
import math
import os
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
CSV_DIR = REPO / "data" / "csv"

SQL_COPT_SS_ACCESS_TOKEN = 1256  # pyodbc access-token attribute
GOLD = "gold"                    # Lakehouse schema holding the curated tables

# Single source of truth for the fields each collection exposes to the UI.
COLS = {
    "profile_search": ["customer_id", "first_name", "last_name", "city", "state", "account_status"],
    "invoices": ["invoice_id", "period_start", "period_end", "due_date", "amount",
                 "paid", "paid_date", "is_first_bill"],
    "work_orders": ["work_order_id", "type", "priority", "status", "opened_date",
                    "closed_date", "resolution"],
    "usage_data": ["usage_date", "gb_used"],
    "usage_voice": ["usage_date", "minutes_used"],
    "churn": ["customer_id", "account_id", "churn_probability", "risk_band",
              "top_reason", "scored_date"],
}


def _json_safe(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, float) and math.isnan(v):
        return ""
    return v


# ============================ Provider interface ============================

class DataProvider:
    """Uniform data surface. Implementations return JSON-safe primitives."""

    name = "base"

    def search_customers(self, query: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_profile(self, customer_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError

    def account_id_for(self, customer_id: str) -> Optional[str]:
        raise NotImplementedError

    def get_invoices(self, account_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_work_orders(self, account_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_usage_data(self, account_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_usage_voice(self, account_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_churn(self, customer_id: str) -> dict[str, Any]:
        raise NotImplementedError


# ============================ Local CSV provider ============================

class LocalCsvProvider(DataProvider):
    name = "local"

    @staticmethod
    @lru_cache(maxsize=1)
    def _raw():
        import pandas as pd

        def rd(name):
            try:
                return pd.read_csv(CSV_DIR / f"{name}.csv")
            except Exception:  # noqa: BLE001
                return None
        names = ["dim_customer", "dim_account", "dim_geography", "fact_subscription",
                 "fact_invoice", "fact_work_order", "fact_usage_data", "fact_usage_voice",
                 "ml_churn_score", "ml_crosssell_reco"]
        return {n: rd(n) for n in names}

    @staticmethod
    @lru_cache(maxsize=1)
    def _customer_360():
        R = LocalCsvProvider._raw()
        c, a, g = R["dim_customer"], R["dim_account"], R["dim_geography"]
        sub, inv = R["fact_subscription"], R["fact_invoice"]
        ch, xs = R["ml_churn_score"], R["ml_crosssell_reco"]

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
              .merge(xs[["account_id", "recommended_product_id", "score"]],
                     on="account_id", how="left"))
        df = df.rename(columns={"status": "account_status", "top_reason": "churn_top_reason",
                                "recommended_product_id": "top_crosssell_product",
                                "score": "top_crosssell_score"})
        return df.fillna("")

    def search_customers(self, query, limit):
        df = self._customer_360()
        q = query.lower()
        mask = (df.customer_id.str.lower().str.contains(q)
                | df.last_name.str.lower().str.contains(q)
                | df.first_name.str.lower().str.contains(q))
        return df[mask][COLS["profile_search"]].head(limit).to_dict("records")

    def get_profile(self, customer_id):
        df = self._customer_360()
        hit = df[df.customer_id == customer_id]
        if hit.empty:
            return None
        return {k: _json_safe(v) for k, v in hit.iloc[0].to_dict().items()}

    def account_id_for(self, customer_id):
        a = self._raw().get("dim_account")
        if a is None:
            return None
        hit = a[a.customer_id == customer_id]
        return None if hit.empty else str(hit.iloc[0]["account_id"])

    def _coll(self, table, key, key_val, sort_col, cols, ascending=True):
        df = self._raw().get(table)
        if df is None:
            return []
        df = df[df[key] == key_val]
        if sort_col in df.columns:
            df = df.sort_values(sort_col, ascending=ascending)
        keep = [c for c in cols if c in df.columns]
        return [{c: _json_safe(v) for c, v in r.items()} for r in df[keep].to_dict("records")]

    def get_invoices(self, account_id):
        return self._coll("fact_invoice", "account_id", account_id, "period_end",
                          COLS["invoices"], ascending=False)

    def get_work_orders(self, account_id):
        return self._coll("fact_work_order", "account_id", account_id, "opened_date",
                          COLS["work_orders"], ascending=False)

    def get_usage_data(self, account_id):
        return self._coll("fact_usage_data", "account_id", account_id, "usage_date",
                          COLS["usage_data"])

    def get_usage_voice(self, account_id):
        return self._coll("fact_usage_voice", "account_id", account_id, "usage_date",
                          COLS["usage_voice"])

    def get_churn(self, customer_id):
        ch = self._raw().get("ml_churn_score")
        if ch is None:
            return {}
        hit = ch[ch.customer_id == customer_id]
        if hit.empty:
            return {}
        return {k: _json_safe(v) for k, v in hit.iloc[0].to_dict().items()}


# ============================ Fabric SQL provider ============================

class FabricSqlProvider(DataProvider):
    name = "live"

    def _conn(self):
        import pyodbc
        server = os.environ["FABRIC_SQL_ENDPOINT"]
        database = os.environ["FABRIC_LAKEHOUSE_NAME"]
        conn_str = (
            "Driver={ODBC Driver 18 for SQL Server};"
            f"Server={server};Database={database};Encrypt=yes;TrustServerCertificate=no;"
        )
        from azure.identity import DefaultAzureCredential
        tok = DefaultAzureCredential().get_token("https://database.windows.net/.default").token
        b = tok.encode("utf-16-le")
        token_struct = struct.pack("=i", len(b)) + b
        return pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})

    def _query(self, sql: str, params: tuple) -> list[dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, *params)
            cols = [d[0] for d in cur.description]
            return [{c: _json_safe(v) for c, v in zip(cols, r)} for r in cur.fetchall()]

    def search_customers(self, query, limit):
        like = f"%{query}%"
        cols = ", ".join(COLS["profile_search"])
        return self._query(
            f"SELECT TOP (?) {cols} FROM {GOLD}.customer_360 "
            "WHERE customer_id LIKE ? OR last_name LIKE ? OR first_name LIKE ?",
            (limit, like, like, like))

    def get_profile(self, customer_id):
        rows = self._query(
            f"SELECT * FROM {GOLD}.customer_360 WHERE customer_id = ?", (customer_id,))
        return rows[0] if rows else None

    def account_id_for(self, customer_id):
        rows = self._query(
            f"SELECT TOP 1 account_id FROM {GOLD}.customer_360 WHERE customer_id = ?",
            (customer_id,))
        return str(rows[0]["account_id"]) if rows else None

    def get_invoices(self, account_id):
        cols = ", ".join(COLS["invoices"])
        return self._query(
            f"SELECT {cols} FROM {GOLD}.fact_invoice WHERE account_id = ? "
            "ORDER BY period_end DESC", (account_id,))

    def get_work_orders(self, account_id):
        cols = ", ".join(COLS["work_orders"])
        return self._query(
            f"SELECT {cols} FROM {GOLD}.fact_work_order WHERE account_id = ? "
            "ORDER BY opened_date DESC", (account_id,))

    def get_usage_data(self, account_id):
        cols = ", ".join(COLS["usage_data"])
        return self._query(
            f"SELECT {cols} FROM {GOLD}.fact_usage_data WHERE account_id = ? "
            "ORDER BY usage_date", (account_id,))

    def get_usage_voice(self, account_id):
        cols = ", ".join(COLS["usage_voice"])
        return self._query(
            f"SELECT {cols} FROM {GOLD}.fact_usage_voice WHERE account_id = ? "
            "ORDER BY usage_date", (account_id,))

    def get_churn(self, customer_id):
        cols = ", ".join(COLS["churn"])
        rows = self._query(
            f"SELECT TOP 1 {cols} FROM {GOLD}.ml_churn_score WHERE customer_id = ?",
            (customer_id,))
        return rows[0] if rows else {}


# ============================ Provider selection ============================

def _live_available() -> bool:
    if not (os.environ.get("FABRIC_SQL_ENDPOINT") and os.environ.get("FABRIC_LAKEHOUSE_NAME")):
        return False
    try:
        import pyodbc  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def mode() -> str:
    return "live" if _live_available() else "local"


@lru_cache(maxsize=2)
def _provider_for(m: str) -> DataProvider:
    return FabricSqlProvider() if m == "live" else LocalCsvProvider()


def _provider() -> DataProvider:
    return _provider_for(mode())


# ============================ Public API (stable) ============================

def get_profile(customer_id: str) -> Optional[dict[str, Any]]:
    return _provider().get_profile(customer_id)


def search_customers(query: str, limit: int = 10) -> list[dict[str, Any]]:
    return _provider().search_customers(query, limit)


def get_account_detail(customer_id: str) -> Optional[dict[str, Any]]:
    """Rich line-of-business view: profile + invoices, work orders, usage series, churn."""
    p = _provider()
    profile = p.get_profile(customer_id)
    if not profile:
        return None
    account_id = profile.get("account_id") or p.account_id_for(customer_id)
    detail = {"profile": profile, "source": p.name, "invoices": [], "work_orders": [],
              "usage_data": [], "usage_voice": [], "churn": {}}
    if not account_id:
        return detail
    detail["invoices"] = p.get_invoices(account_id)
    detail["work_orders"] = p.get_work_orders(account_id)
    detail["usage_data"] = p.get_usage_data(account_id)
    detail["usage_voice"] = p.get_usage_voice(account_id)
    detail["churn"] = p.get_churn(customer_id)
    return detail
