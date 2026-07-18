"""
Synthetic telco dataset generator.

Generates a referentially-consistent set of tables (customers, accounts, billing,
usage, service, engagement, ML scores) for the Fabric + Foundry demo and writes them
to local CSV + Parquet files that are committed to the repo.

Usage:
    python generate.py --customers 1000
    python generate.py --customers 10000 --seed 7 --out ../data
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Allow running from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generators import PIPELINE  # noqa: E402
from generators.common import make_context  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "config.yaml"
DEFAULT_OUT = HERE.parent / "data"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Generate synthetic telco demo data.")
    p.add_argument("--customers", type=int, default=None, help="Number of customers (overrides config).")
    p.add_argument("--seed", type=int, default=None, help="Random seed (overrides config).")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to config.yaml.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory (data/).")
    p.add_argument("--formats", nargs="+", default=["csv", "parquet"],
                   choices=["csv", "parquet"], help="Output formats to write.")
    return p.parse_args(argv)


def load_config(path: Path, customers, seed) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if customers is not None:
        cfg["customers"] = customers
    if seed is not None:
        cfg["seed"] = seed
    return cfg


def write_frames(frames: dict, out_dir: Path, formats) -> dict:
    csv_dir = out_dir / "csv"
    pq_dir = out_dir / "parquet"
    csv_dir.mkdir(parents=True, exist_ok=True)
    pq_dir.mkdir(parents=True, exist_ok=True)

    counts = {}
    for name, df in frames.items():
        counts[name] = int(len(df))
        if "csv" in formats:
            df.to_csv(csv_dir / f"{name}.csv", index=False)
        if "parquet" in formats:
            df.to_parquet(pq_dir / f"{name}.parquet", index=False)
    return counts


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config, args.customers, args.seed)
    ctx = make_context(cfg)

    print(f"Generating synthetic telco data: {ctx.n_customers} customers, seed={ctx.seed}, "
          f"as_of={ctx.as_of.isoformat()}")

    for name, module in PIPELINE:
        module.generate(ctx)
        print(f"  [{name}] ok")

    counts = write_frames(ctx.frames, args.out, args.formats)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "customers": ctx.n_customers,
        "seed": ctx.seed,
        "as_of_date": ctx.as_of.isoformat(),
        "formats": args.formats,
        "tables": counts,
        "total_rows": int(sum(counts.values())),
    }
    with open(args.out / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\nRow counts:")
    for name in sorted(counts):
        print(f"  {name:24s} {counts[name]:>8,}")
    print(f"\nTotal rows: {manifest['total_rows']:,}")
    print(f"Output written to: {args.out.resolve()}")
    print(f"Manifest: {(args.out / 'manifest.json').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
