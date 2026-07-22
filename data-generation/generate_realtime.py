"""
Generate the real-time (Eventhouse / KQL) synthetic data.

Reads the **committed** Lakehouse customers in `data/csv/` and writes two customer-keyed CSVs
for the KQL tables to `data/kql/`:

    outage_events.csv   -> OutageEvents  (outage information by customer)
    web_sessions.csv    -> WebSessions   (web browser session information)

It does NOT regenerate customers — run `generate.py` first if `data/csv/` is empty. Event
timestamps anchor to `--as-of` (default 2026-06-30) so they line up with the batch data.

Usage:
    python generate_realtime.py
    python generate_realtime.py --seed 7 --as-of 2026-06-30 --out ../data
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generators import realtime  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "data"

# Volume knobs (kept modest so chunked `.ingest inline` stays practical).
CONFIG = {
    "outage_affected_rate": 0.18,
    "outage_recent_geo_boost": 3.0,
    "outage_window_days": 30,
    "session_customer_rate": 0.40,
    "session_window_days": 30,
    "session_max_per_customer": 8,
}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Generate real-time (KQL) telco demo data.")
    p.add_argument("--seed", type=int, default=42, help="Random seed (default 42).")
    p.add_argument("--as-of", default="2026-06-30",
                   help="Anchor date for event timestamps (YYYY-MM-DD, default 2026-06-30).")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Data directory (default ../data).")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    csv_dir = args.out / "csv"
    kql_dir = args.out / "kql"
    if not (csv_dir / "dim_customer.csv").exists():
        print(f"ERROR: {csv_dir/'dim_customer.csv'} not found. Run generate.py first.",
              file=sys.stderr)
        return 1
    kql_dir.mkdir(parents=True, exist_ok=True)

    as_of = datetime.strptime(args.as_of, "%Y-%m-%d")
    rng = np.random.default_rng(args.seed)
    print(f"Generating real-time KQL data: seed={args.seed}, as_of={as_of.date().isoformat()}")

    outages = realtime.generate_outage_events(csv_dir, as_of, rng, CONFIG)
    sessions = realtime.generate_web_sessions(csv_dir, as_of, rng, CONFIG)

    outages.to_csv(kql_dir / "outage_events.csv", index=False)
    sessions.to_csv(kql_dir / "web_sessions.csv", index=False)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "as_of_date": as_of.date().isoformat(),
        "tables": {
            "OutageEvents": {"file": "outage_events.csv", "rows": int(len(outages)),
                             "columns": realtime.OUTAGE_COLUMNS},
            "WebSessions": {"file": "web_sessions.csv", "rows": int(len(sessions)),
                            "columns": realtime.WEBSESSION_COLUMNS},
        },
    }
    (kql_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"  OutageEvents  {len(outages):>7,} rows -> {kql_dir/'outage_events.csv'}")
    print(f"  WebSessions   {len(sessions):>7,} rows -> {kql_dir/'web_sessions.csv'}")
    print(f"  manifest      -> {kql_dir/'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
