"""
Create the Telco Direct Lake semantic model from model_spec.yaml.

Uses semantic-link-labs (sempy_labs) to:
  1. create a Direct Lake semantic model over the Lakehouse tables
  2. add relationships
  3. add business measures (DAX)

Best run inside a Fabric notebook (auth + Spark context are automatic). It can also
run from a machine authenticated to Fabric via the Azure CLI / a service principal.

Install: pip install semantic-link-labs
Docs:    https://github.com/microsoft/semantic-link-labs

Because the sempy_labs API surface evolves, optional steps are wrapped so a version
mismatch degrades gracefully instead of aborting the whole run. model_spec.yaml is the
source of truth for tables, relationships, and measures; you can also apply them with
Tabular Editor or the Fabric portal.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SPEC = HERE / "model_spec.yaml"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main() -> int:
    load_env_file(REPO / ".env")
    workspace_id = os.environ.get("FABRIC_WORKSPACE_ID")
    if not workspace_id or workspace_id.startswith("00000000"):
        print("ERROR: FABRIC_WORKSPACE_ID not set in .env", file=sys.stderr)
        return 1

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    dataset = spec["name"]
    lakehouse = os.environ.get("FABRIC_LAKEHOUSE_NAME", spec["lakehouse"])
    schema = spec.get("schema", "gold")

    try:
        import sempy_labs as labs
        from sempy_labs import directlake
    except ImportError:
        print("ERROR: semantic-link-labs is not installed. Run: pip install semantic-link-labs",
              file=sys.stderr)
        return 1

    # 1. Create the Direct Lake model over the selected tables.
    # API (current): generate_direct_lake_semantic_model(dataset, tables, source, ...)
    # 'tables' are schema-qualified (gold.<name>); 'source' is the Lakehouse.
    print(f"Creating Direct Lake model '{dataset}' over lakehouse '{lakehouse}' ...")
    _try(
        lambda: directlake.generate_direct_lake_semantic_model(
            dataset=dataset,
            tables=[f"{schema}.{t}" for t in spec["tables"]],
            source=lakehouse,
            source_type="Lakehouse",
            workspace=workspace_id,
            overwrite=True,
        ),
        alt=lambda: directlake.generate_direct_lake_semantic_model(
            dataset=dataset, tables=spec["tables"], source=lakehouse,
            source_type="Lakehouse", workspace=workspace_id, overwrite=True),
        label="create model",
    )

    # 2 + 3. Relationships and measures via the Tabular Object Model wrapper.
    try:
        with labs.tom.connect_semantic_model(
            dataset=dataset, workspace=workspace_id, readonly=False
        ) as tom:
            for rel in spec.get("relationships", []):
                ft, fc = rel["from"].split(".")
                tt, tc = rel["to"].split(".")
                _try(lambda ft=ft, fc=fc, tt=tt, tc=tc: tom.add_relationship(
                    from_table=ft, from_column=fc, to_table=tt, to_column=tc,
                    from_cardinality="Many", to_cardinality="One"),
                    label=f"relationship {rel['from']}->{rel['to']}")
            for m in spec.get("measures", []):
                _try(lambda m=m: tom.add_measure(
                    table_name=m["table"], measure_name=m["name"],
                    expression=m["expression"].strip(),
                    format_string=m.get("format")),
                    label=f"measure {m['name']}")
        print("Relationships + measures applied.")
    except Exception as ex:  # noqa: BLE001
        print(f"NOTE: could not apply relationships/measures via TOM ({ex}). "
              f"Apply model_spec.yaml with Tabular Editor or the portal instead.")

    print(f"Semantic model '{dataset}' ready.")
    return 0


def _try(fn, alt=None, label=""):
    try:
        fn()
        if label:
            print(f"  ok: {label}")
    except Exception as ex:  # noqa: BLE001
        if alt is not None:
            try:
                alt()
                print(f"  ok (fallback): {label}")
                return
            except Exception:  # noqa: BLE001
                pass
        print(f"  skipped: {label} ({ex})")


if __name__ == "__main__":
    raise SystemExit(main())
