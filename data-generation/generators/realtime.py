"""
Real-time (Eventhouse / KQL) synthetic data generators.

Unlike the Lakehouse pipeline (which regenerates every table), these generators **read the
already-committed** `data/csv` customers so the real-time data is keyed by the same
`customer_id` values and lines up with the batch data. Two frames are produced:

  OutageEvents  - outage information by customer
  WebSessions   - web browser session information

Column value formats are chosen to be KQL- and ontology-binding friendly:
  * ids / categoricals -> string
  * timestamps         -> ISO-8601 (KQL `datetime`)
  * continuous numbers -> float (KQL `real` -> ontology Double); never Decimal
  * counts             -> int (KQL `long`)
  * flags              -> bool written as `true` / `false`
String fields never contain commas (so chunked `.ingest inline` CSV stays valid).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Schemas are the single source of truth shared with the provisioning script. Order matters:
# the CSV columns, the KQL table columns, and the inline-ingest order all follow these lists.
OUTAGE_COLUMNS = [
    ("event_id", "string"),
    ("customer_id", "string"),
    ("account_id", "string"),
    ("geo_id", "string"),
    ("event_time", "datetime"),
    ("outage_type", "string"),
    ("severity", "string"),
    ("status", "string"),
    ("affected_service", "string"),
    ("duration_minutes", "real"),
    ("restored_time", "datetime"),
    ("reported_by_customer", "bool"),
]

WEBSESSION_COLUMNS = [
    ("session_id", "string"),
    ("customer_id", "string"),
    ("session_start", "datetime"),
    ("session_end", "datetime"),
    ("duration_seconds", "real"),
    ("device_type", "string"),
    ("browser", "string"),
    ("os", "string"),
    ("entry_page", "string"),
    ("exit_page", "string"),
    ("page_views", "long"),
    ("referrer", "string"),
    ("authenticated", "bool"),
    ("converted", "bool"),
]

_OUTAGE_TYPES = ["Fiber cut", "Power loss", "Equipment failure", "Weather", "Congestion"]
_SEVERITY = {"Minor": 0.5, "Major": 0.35, "Critical": 0.15}
_STATUS = ["Detected", "Investigating", "Restoring", "Resolved"]

_DEVICES = {"Desktop": 0.45, "Mobile": 0.45, "Tablet": 0.10}
_DEVICE_OS = {
    "Desktop": {"Windows": 0.7, "macOS": 0.3},
    "Mobile": {"iOS": 0.5, "Android": 0.5},
    "Tablet": {"iOS": 0.6, "Android": 0.4},
}
_DEVICE_BROWSER = {
    "Windows": {"Chrome": 0.6, "Edge": 0.35, "Firefox": 0.05},
    "macOS": {"Safari": 0.5, "Chrome": 0.45, "Firefox": 0.05},
    "iOS": {"Safari": 0.8, "Chrome": 0.2},
    "Android": {"Chrome": 0.9, "Firefox": 0.1},
}
_PAGES = ["/home", "/billing", "/support", "/plans", "/outage-status", "/account", "/upgrade"]
_REFERRERS = {"Direct": 0.4, "Search": 0.3, "Email": 0.15, "Social": 0.1, "Ad": 0.05}

# category (dim_product) -> friendly service label used in OutageEvents.affected_service
_CATEGORY_SERVICE = {"internet": "Internet", "mobile": "Mobile", "voice": "Voice", "tv": "TV"}


def _iso(dt: datetime) -> str:
    return dt.isoformat(sep=" ", timespec="seconds")


def _customer_account_map(csv_dir: Path) -> dict[str, str]:
    """Map customer_id -> account_id (one account per customer in this dataset)."""
    try:
        acct = pd.read_csv(csv_dir / "dim_account.csv", usecols=["account_id", "customer_id"])
    except Exception:  # noqa: BLE001
        return {}
    return dict(zip(acct["customer_id"].astype(str), acct["account_id"].astype(str)))


def _customer_services(csv_dir: Path) -> dict[str, list[str]]:
    """Map customer_id -> list of friendly service labels from their active products."""
    try:
        acct = pd.read_csv(csv_dir / "dim_account.csv", usecols=["account_id", "customer_id"])
        sub = pd.read_csv(csv_dir / "fact_subscription.csv",
                          usecols=["account_id", "product_id", "status"])
        prod = pd.read_csv(csv_dir / "dim_product.csv", usecols=["product_id", "category"])
    except Exception:  # noqa: BLE001
        return {}
    sub = sub[sub["status"] == "active"]
    m = (sub.merge(acct, on="account_id", how="left")
            .merge(prod, on="product_id", how="left"))
    m["service"] = m["category"].map(_CATEGORY_SERVICE).fillna("Internet")
    return m.groupby("customer_id")["service"].agg(lambda s: sorted(set(s))).to_dict()


def _recent_outage_geos(csv_dir: Path, as_of, window_days: int) -> set[str]:
    """geo_ids that had an outage within `window_days` of as_of (to bias realtime events)."""
    try:
        out = pd.read_csv(csv_dir / "fact_outage.csv", usecols=["geo_id", "start_time"])
    except Exception:  # noqa: BLE001
        return set()
    start = pd.to_datetime(out["start_time"], errors="coerce").dt.date
    recent = out[(pd.Timestamp(as_of).date() - start).apply(
        lambda d: getattr(d, "days", 10**6)) <= window_days]
    return set(recent["geo_id"].dropna().astype(str))


def generate_outage_events(csv_dir: Path, as_of: datetime, rng: np.random.Generator,
                           cfg: dict) -> pd.DataFrame:
    cust = pd.read_csv(csv_dir / "dim_customer.csv", usecols=["customer_id", "geo_id"])
    services = _customer_services(csv_dir)
    accounts = _customer_account_map(csv_dir)
    window = int(cfg.get("outage_window_days", 30))
    recent_geos = _recent_outage_geos(csv_dir, as_of, window)

    # Weight: customers in a recently-outage-affected geo are far more likely to get events.
    affected_rate = float(cfg.get("outage_affected_rate", 0.18))
    boost = float(cfg.get("outage_recent_geo_boost", 3.0))
    base = np.full(len(cust), affected_rate)
    in_recent = cust["geo_id"].astype(str).isin(recent_geos).to_numpy()
    prob = np.clip(np.where(in_recent, base * boost, base), 0, 1)
    picked = cust[rng.random(len(cust)) < prob].reset_index(drop=True)

    rows = []
    for _, c in picked.iterrows():
        n_events = int(rng.integers(1, 3))  # 1-2 events
        cust_services = services.get(c["customer_id"], ["Internet"])
        for _ in range(n_events):
            # bias ~55% into the recent window (last `window` days), rest older within 60d
            if rng.random() < 0.55:
                mins_ago = int(rng.integers(5, window * 24 * 60))
            else:
                mins_ago = int(rng.integers(window * 24 * 60, 60 * 24 * 60))
            event_time = as_of - timedelta(minutes=mins_ago)
            duration = float(round(rng.gamma(shape=2.0, scale=45.0), 1))  # minutes
            ended = event_time + timedelta(minutes=duration)
            resolved = ended <= as_of and rng.random() < 0.9
            status = "Resolved" if resolved else rng.choice(_STATUS[:3])
            rows.append({
                "event_id": None,
                "customer_id": c["customer_id"],
                "account_id": accounts.get(str(c["customer_id"]), ""),
                "geo_id": c["geo_id"],
                "event_time": _iso(event_time),
                "outage_type": rng.choice(_OUTAGE_TYPES),
                "severity": rng.choice(list(_SEVERITY), p=list(_SEVERITY.values())),
                "status": str(status),
                "affected_service": rng.choice(cust_services),
                "duration_minutes": duration,
                "restored_time": _iso(ended) if resolved else "",
                "reported_by_customer": bool(rng.random() < 0.45),
            })
    df = pd.DataFrame(rows, columns=[c for c, _ in OUTAGE_COLUMNS])
    if not df.empty:
        df["event_id"] = [f"OEV{i:012d}" for i in range(1, len(df) + 1)]
    return df


def generate_web_sessions(csv_dir: Path, as_of: datetime, rng: np.random.Generator,
                          cfg: dict) -> pd.DataFrame:
    cust = pd.read_csv(csv_dir / "dim_customer.csv", usecols=["customer_id"])
    window = int(cfg.get("session_window_days", 30))
    session_rate = float(cfg.get("session_customer_rate", 0.40))
    max_sessions = int(cfg.get("session_max_per_customer", 8))

    picked = cust[rng.random(len(cust)) < session_rate].reset_index(drop=True)
    rows = []
    for _, c in picked.iterrows():
        n = int(rng.integers(1, max_sessions + 1))
        for _ in range(n):
            mins_ago = int(rng.integers(5, window * 24 * 60))
            start = as_of - timedelta(minutes=mins_ago)
            page_views = int(rng.integers(1, 13))
            duration = float(round(page_views * rng.uniform(8, 45), 1))  # seconds
            end = start + timedelta(seconds=duration)
            device = rng.choice(list(_DEVICES), p=list(_DEVICES.values()))
            os_name = _pick(rng, _DEVICE_OS[device])
            browser = _pick(rng, _DEVICE_BROWSER[os_name])
            entry = rng.choice(_PAGES)
            exit_page = entry if page_views == 1 else rng.choice(_PAGES)
            authed = bool(rng.random() < 0.6)
            converted = bool(authed and rng.random() < 0.25)
            rows.append({
                "session_id": None,
                "customer_id": c["customer_id"],
                "session_start": _iso(start),
                "session_end": _iso(end),
                "duration_seconds": duration,
                "device_type": device,
                "browser": browser,
                "os": os_name,
                "entry_page": str(entry),
                "exit_page": str(exit_page),
                "page_views": page_views,
                "referrer": _pick(rng, _REFERRERS),
                "authenticated": authed,
                "converted": converted,
            })
    df = pd.DataFrame(rows, columns=[c for c, _ in WEBSESSION_COLUMNS])
    if not df.empty:
        df["session_id"] = [f"WSN{i:012d}" for i in range(1, len(df) + 1)]
    return df


def _pick(rng: np.random.Generator, mapping: dict) -> str:
    keys = list(mapping)
    p = np.array(list(mapping.values()), dtype=float)
    return str(rng.choice(keys, p=p / p.sum()))
