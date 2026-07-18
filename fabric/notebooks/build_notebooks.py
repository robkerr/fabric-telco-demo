"""
Builds the Fabric notebooks (.ipynb) for the medallion pipeline.

Keeping the notebook *source* here (plain Python) guarantees valid, reproducible
notebook JSON. Run this to (re)generate the .ipynb files, which are the portable
artifacts you upload to / run in Microsoft Fabric:

    python fabric/notebooks/build_notebooks.py

Notebooks produced:
    01_setup_lakehouse.ipynb      - validate lakehouse + landing files
    02_load_bronze.ipynb          - raw parquet -> bronze_* Delta tables
    03_build_silver_gold.ipynb    - curated dim_/fact_ tables (clean names)
    04_ml_scores.ipynb            - churn + cross-sell gold tables + customer_360
    05_create_data_agent.ipynb    - create & publish the Fabric Data Agent (run in Fabric)
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DATA_AGENT_CONFIG = HERE.parent / "data-agent" / "config.yaml"

# All tables produced by the data generator (must match data/parquet/*.parquet).
TABLES = [
    "dim_geography", "dim_product", "dim_plan", "dim_device", "dim_promotion",
    "dim_customer", "dim_account", "fact_subscription", "fact_invoice",
    "fact_invoice_line", "fact_usage_data", "fact_usage_voice", "fact_coverage",
    "fact_outage", "fact_service_metric", "fact_work_order", "fact_appointment",
    "fact_contact", "fact_offer", "fact_feedback",
    "ml_churn_score", "ml_crosssell_reco",
]
# Curated (gold) tables built in 03 with clean names (ml + customer_360 handled in 04).
CURATED = [t for t in TABLES if not t.startswith("ml_")]


def md(*lines):
    return {"cell_type": "markdown", "metadata": {}, "source": _src(lines)}


def code(*lines):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": _src(lines)}


def _src(lines):
    text = "\n".join(lines)
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


def notebook(cells):
    return {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {
            "language_info": {"name": "python"},
            "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
        },
        "cells": cells,
    }


def write(name, nb):
    path = HERE / name
    path.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print(f"wrote {path.name} ({len(nb['cells'])} cells)")


# ----------------------------------------------------------------------------
# 01 - setup / validate
# ----------------------------------------------------------------------------
def nb_01():
    return notebook([
        md("# 01 - Setup & validate Lakehouse",
           "",
           "Confirms a Lakehouse is attached and the landing Parquet files are present.",
           "Upload `data/parquet/*.parquet` to the Lakehouse **Files/landing/** folder first",
           "(the `10_provision_fabric.ps1` script does this automatically)."),
        code("import notebookutils",
             "LANDING = 'Files/landing'",
             "try:",
             "    files = [f.name for f in notebookutils.fs.ls(LANDING)]",
             "except Exception as ex:",
             "    raise RuntimeError(",
             "        f\"Could not list {LANDING}. Make sure a default Lakehouse is attached \"",
             "        f\"(the 20_load_data.ps1 job sets executionData.configuration.defaultLakehouse) \"",
             "        f\"and that the parquet files were uploaded by 10_provision_fabric.ps1. Root cause: {ex}\")",
             "print(f'{len(files)} files in {LANDING}:')",
             "for f in sorted(files):",
             "    print('  ', f)"),
        code("# Sanity check: warn (do not fail) if any expected landing file is missing,",
             "# so the pipeline can still proceed for the tables that are present.",
             f"expected = {sorted(TABLES)!r}",
             "present = {f.replace('.parquet','') for f in files}",
             "missing = [t for t in expected if t not in present]",
             "if missing:",
             "    print('WARNING - missing landing files:', missing)",
             "else:",
             "    print('All expected landing files present.')"),
    ])


# ----------------------------------------------------------------------------
# 02 - bronze
# ----------------------------------------------------------------------------
def nb_02():
    return notebook([
        md("# 02 - Load Bronze",
           "",
           "Reads each raw Parquet file from `Files/landing/` and writes it as a",
           "Delta table named `bronze_<table>`."),
        code("LANDING = 'Files/landing'",
             f"tables = {TABLES!r}",
             "",
             "for t in tables:",
             "    df = spark.read.parquet(f'{LANDING}/{t}.parquet')",
             "    (df.write.format('delta').mode('overwrite')",
             "        .option('overwriteSchema', 'true').saveAsTable(f'bronze_{t}'))",
             "    print(f'bronze_{t:24s} {df.count():>8,} rows')"),
        code("print('Bronze load complete.')"),
    ])


# ----------------------------------------------------------------------------
# 03 - silver / gold curated
# ----------------------------------------------------------------------------
def nb_03():
    # Per-table date/timestamp casts for nicer SQL-endpoint types.
    date_cols = {
        "dim_account": ["open_date", "close_date"],
        "dim_customer": ["date_of_birth"],
        "fact_subscription": ["start_date", "end_date"],
        "fact_invoice": ["period_start", "period_end", "due_date", "paid_date"],
        "fact_offer": ["presented_date"],
        "fact_feedback": ["feedback_date"],
        "fact_work_order": ["opened_date", "closed_date"],
        "fact_usage_data": ["usage_date"],
        "fact_usage_voice": ["usage_date"],
        "fact_service_metric": ["metric_date"],
    }
    ts_cols = {
        "fact_outage": ["start_time", "end_time"],
        "fact_contact": ["contact_ts"],
    }
    return notebook([
        md("# 03 - Build Silver/Gold curated tables",
           "",
           "Promotes `bronze_*` to curated tables with clean business names",
           "(`dim_*`, `fact_*`) and casts date/timestamp columns for the SQL endpoint.",
           "ML tables and `customer_360` are built in notebook 04."),
        code("from pyspark.sql import functions as F",
             "",
             f"curated = {CURATED!r}",
             f"date_cols = {date_cols!r}",
             f"ts_cols = {ts_cols!r}",
             "",
             "for t in curated:",
             "    df = spark.table(f'bronze_{t}')",
             "    for c in date_cols.get(t, []):",
             "        if c in df.columns:",
             "            df = df.withColumn(c, F.to_date(F.col(c)))",
             "    for c in ts_cols.get(t, []):",
             "        if c in df.columns:",
             "            df = df.withColumn(c, F.to_timestamp(F.col(c)))",
             "    (df.write.format('delta').mode('overwrite')",
             "        .option('overwriteSchema', 'true').saveAsTable(t))",
             "    print(f'{t:24s} {df.count():>8,} rows')"),
        code("print('Curated dim/fact tables built.')"),
    ])


# ----------------------------------------------------------------------------
# 04 - ML scores + customer_360
# ----------------------------------------------------------------------------
def nb_04():
    churn_sql = """
CREATE OR REPLACE TABLE ml_churn_score AS
WITH unpaid AS (
    SELECT account_id, COUNT(*) AS unpaid_ct
    FROM fact_invoice WHERE paid = false GROUP BY account_id
),
uptime AS (
    SELECT account_id, AVG(uptime_pct) AS avg_uptime
    FROM fact_service_metric GROUP BY account_id
),
csat AS (
    SELECT account_id, AVG(csat) AS avg_csat
    FROM fact_feedback GROUP BY account_id
),
cancels AS (
    SELECT customer_id, COUNT(*) AS cancel_ct
    FROM fact_contact WHERE reason = 'cancel_request' GROUP BY customer_id
),
scored AS (
    SELECT
        a.customer_id, a.account_id,
        LEAST(0.98, GREATEST(0.01,
            0.10
            + CASE WHEN a.status = 'suspended' THEN 0.25 ELSE 0 END
            + LEAST(0.30, 0.10 * COALESCE(u.unpaid_ct, 0))
            + CASE WHEN COALESCE(up.avg_uptime, 100) < 99.0 THEN 0.20 ELSE 0 END
            + CASE WHEN COALESCE(cs.avg_csat, 5) <= 2.5 THEN 0.20 ELSE 0 END
            + CASE WHEN COALESCE(cn.cancel_ct, 0) > 0 THEN 0.25 ELSE 0 END
            + CASE WHEN c.tenure_months < 6 THEN 0.10
                   WHEN c.tenure_months > 48 THEN -0.05 ELSE 0 END
            + CASE WHEN a.autopay = false THEN 0.05 ELSE 0 END
        )) AS churn_probability,
        CASE
            WHEN COALESCE(cn.cancel_ct,0) > 0 THEN 'cancellation intent'
            WHEN a.status = 'suspended' THEN 'account suspended'
            WHEN COALESCE(up.avg_uptime,100) < 99.0 THEN 'degraded service'
            WHEN COALESCE(cs.avg_csat,5) <= 2.5 THEN 'low satisfaction'
            WHEN COALESCE(u.unpaid_ct,0) > 0 THEN 'unpaid invoices'
            WHEN c.tenure_months < 6 THEN 'new/short tenure'
            ELSE 'stable account'
        END AS top_reason
    FROM dim_account a
    JOIN dim_customer c ON a.customer_id = c.customer_id
    LEFT JOIN unpaid u ON a.account_id = u.account_id
    LEFT JOIN uptime up ON a.account_id = up.account_id
    LEFT JOIN csat cs ON a.account_id = cs.account_id
    LEFT JOIN cancels cn ON a.customer_id = cn.customer_id
)
SELECT customer_id, account_id,
       ROUND(churn_probability, 3) AS churn_probability,
       CASE WHEN churn_probability >= 0.55 THEN 'High'
            WHEN churn_probability >= 0.30 THEN 'Medium' ELSE 'Low' END AS risk_band,
       top_reason,
       CURRENT_DATE() AS scored_date
FROM scored
""".strip()

    xsell_sql = """
CREATE OR REPLACE TABLE ml_crosssell_reco AS
WITH owned AS (
    SELECT account_id, collect_set(product_id) AS products
    FROM fact_subscription GROUP BY account_id
)
SELECT
    a.account_id,
    CASE WHEN NOT array_contains(o.products, 'PROD_MOB') THEN 'PROD_MOB'
         WHEN NOT array_contains(o.products, 'PROD_TV')  THEN 'PROD_TV'
         ELSE 'PROD_VOICE' END AS recommended_product_id,
    CASE WHEN NOT array_contains(o.products, 'PROD_MOB') THEN 'PROMO_XSELL_1'
         WHEN NOT array_contains(o.products, 'PROD_TV')  THEN 'PROMO_XSELL_2'
         ELSE NULL END AS recommended_promotion_id,
    ROUND(0.4 + LEAST(c.tenure_months, 60) / 200.0, 3) AS score,
    CASE WHEN NOT array_contains(o.products, 'PROD_MOB')
              THEN 'Internet customer without mobile'
         WHEN NOT array_contains(o.products, 'PROD_TV')
              THEN 'Eligible for TV + internet bundle'
         ELSE 'Add home phone to bundle' END AS rationale,
    CURRENT_DATE() AS scored_date
FROM dim_account a
JOIN dim_customer c ON a.customer_id = c.customer_id
JOIN owned o ON a.account_id = o.account_id
WHERE a.status <> 'cancelled'
  AND NOT (array_contains(o.products, 'PROD_MOB')
           AND array_contains(o.products, 'PROD_TV')
           AND array_contains(o.products, 'PROD_VOICE'))
""".strip()

    c360_sql = """
CREATE OR REPLACE TABLE customer_360 AS
WITH sub_agg AS (
    SELECT account_id,
           COUNT(*) AS active_products,
           ROUND(SUM(mrc), 2) AS total_mrc,
           concat_ws(', ', collect_list(product_id)) AS product_list
    FROM fact_subscription WHERE status = 'active' GROUP BY account_id
),
latest_inv AS (
    SELECT account_id, period_end, amount, due_date, paid, is_first_bill
    FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY period_end DESC) rn
        FROM fact_invoice
    ) WHERE rn = 1
),
balance AS (
    SELECT account_id, ROUND(SUM(amount), 2) AS open_balance
    FROM fact_invoice WHERE paid = false GROUP BY account_id
),
open_wo AS (
    SELECT account_id, COUNT(*) AS open_work_orders
    FROM fact_work_order WHERE status = 'open' GROUP BY account_id
),
last_contact AS (
    SELECT customer_id, MAX(contact_ts) AS last_contact_ts
    FROM fact_contact GROUP BY customer_id
),
recent_outage AS (
    SELECT DISTINCT geo_id FROM fact_outage
    WHERE start_time >= date_sub(current_timestamp(), 14)
)
SELECT
    c.customer_id, a.account_id,
    c.first_name, c.last_name, c.email, c.phone, c.segment,
    c.tenure_months, a.status AS account_status, a.open_date, a.is_new_customer,
    a.autopay, a.credit_class,
    g.city, g.state, g.region, g.zip,
    COALESCE(s.active_products, 0) AS active_products,
    COALESCE(s.total_mrc, 0) AS total_mrc,
    s.product_list,
    li.amount AS last_invoice_amount, li.due_date AS last_invoice_due,
    li.paid AS last_invoice_paid, li.is_first_bill AS last_invoice_is_first_bill,
    COALESCE(b.open_balance, 0) AS open_balance,
    COALESCE(w.open_work_orders, 0) AS open_work_orders,
    lc.last_contact_ts,
    CASE WHEN ro.geo_id IS NOT NULL THEN true ELSE false END AS recent_outage_exposure,
    ch.churn_probability, ch.risk_band, ch.top_reason AS churn_top_reason,
    xs.recommended_product_id AS top_crosssell_product,
    xs.recommended_promotion_id AS top_crosssell_promo,
    xs.score AS top_crosssell_score
FROM dim_customer c
JOIN dim_account a ON c.customer_id = a.customer_id
LEFT JOIN dim_geography g ON c.geo_id = g.geo_id
LEFT JOIN sub_agg s ON a.account_id = s.account_id
LEFT JOIN latest_inv li ON a.account_id = li.account_id
LEFT JOIN balance b ON a.account_id = b.account_id
LEFT JOIN open_wo w ON a.account_id = w.account_id
LEFT JOIN last_contact lc ON c.customer_id = lc.customer_id
LEFT JOIN recent_outage ro ON c.geo_id = ro.geo_id
LEFT JOIN ml_churn_score ch ON c.customer_id = ch.customer_id
LEFT JOIN ml_crosssell_reco xs ON a.account_id = xs.account_id
""".strip()

    return notebook([
        md("# 04 - ML scores + Customer 360 (Gold)",
           "",
           "Computes churn risk and cross-sell recommendations from the curated tables,",
           "then builds the denormalized `customer_360` gold table used by the SQL endpoint",
           "and the Fabric Data Agent."),
        md("## Churn score (rule-based, transparent heuristic)"),
        code("spark.sql('''" + churn_sql + "''')",
             "print('ml_churn_score rows:', spark.table('ml_churn_score').count())",
             "spark.sql('SELECT risk_band, COUNT(*) c FROM ml_churn_score GROUP BY risk_band').show()"),
        md("## Cross-sell recommendations (product-gap logic)"),
        code("spark.sql('''" + xsell_sql + "''')",
             "print('ml_crosssell_reco rows:', spark.table('ml_crosssell_reco').count())",
             "spark.sql('SELECT recommended_product_id, COUNT(*) c FROM ml_crosssell_reco GROUP BY recommended_product_id').show()"),
        md("## Customer 360 (gold serving object)"),
        code("spark.sql('''" + c360_sql + "''')",
             "print('customer_360 rows:', spark.table('customer_360').count())"),
        md("## Validation: sample a new customer with an unpaid first bill"),
        code("spark.sql('''",
             "SELECT customer_id, first_name, last_name, account_status, tenure_months,",
             "       last_invoice_amount, last_invoice_is_first_bill, open_balance,",
             "       risk_band, top_crosssell_product",
             "FROM customer_360",
             "WHERE last_invoice_is_first_bill = true AND last_invoice_paid = false",
             "LIMIT 10''').show(truncate=False)"),
    ])


# ----------------------------------------------------------------------------
# 05 - create & publish the Fabric Data Agent (run inside Fabric)
# ----------------------------------------------------------------------------
def nb_05():
    cfg = yaml.safe_load(DATA_AGENT_CONFIG.read_text(encoding="utf-8"))
    ds = (cfg.get("datasources") or [{}])[0]
    example_queries = [(e["question"], e["query"]) for e in cfg.get("example_queries", [])]

    return notebook([
        md("# 05 - Create & publish the Fabric Data Agent",
           "",
           "Run this **inside Fabric** (it uses the `fabric-data-agent-sdk`, which relies on the",
           "Fabric runtime for auth and .NET). It creates/updates the Telco data agent, attaches",
           "the Lakehouse, sets instructions + example queries, and publishes.",
           "",
           "**Steps:** attach the Telco Lakehouse as the default Lakehouse, then **Run all**. Copy",
           "the printed `DATA_AGENT_ARTIFACT_ID` and `DATA_AGENT_MCP_ENDPOINT` into your local `.env`.",
           "",
           "> This is the supported way to create the data agent (it is not created from the local",
           "> workstation). Config below mirrors `fabric/data-agent/config.yaml`, the source of truth."),
        code("%pip install --quiet fabric-data-agent-sdk"),
        md("## Configuration (mirrors fabric/data-agent/config.yaml)"),
        code(f"NAME = {cfg['name']!r}",
             f"DESCRIPTION = {cfg.get('description', 'Telco data agent')!r}",
             f"LAKEHOUSE_DEFAULT = {ds.get('artifact', 'TelcoLakehouse')!r}  # fallback only",
             f"AI_INSTRUCTIONS = {cfg['ai_instructions']!r}",
             f"DS_INSTRUCTIONS = {ds.get('instructions', '')!r}",
             f"EXAMPLE_QUERIES = {example_queries!r}"),
        md("## Resolve the current workspace + attached Lakehouse",
           "",
           "The Lakehouse is taken from whichever Lakehouse you attach as the notebook's default",
           "(so it works no matter what you named it, e.g. `lh_telco`). `LAKEHOUSE_DEFAULT` is only",
           "used as a fallback if none is attached."),
        code("workspace_id = None",
             "LAKEHOUSE = None",
             "try:",
             "    import notebookutils",
             "    ctx = notebookutils.runtime.context",
             "    workspace_id = ctx.get('currentWorkspaceId')",
             "    LAKEHOUSE = ctx.get('defaultLakehouseName')",
             "except Exception:",
             "    pass",
             "if not workspace_id:",
             "    import sempy.fabric as fabric",
             "    workspace_id = fabric.get_notebook_workspace_id()",
             "if not LAKEHOUSE:",
             "    LAKEHOUSE = LAKEHOUSE_DEFAULT",
             "    print(f'WARNING: no default Lakehouse detected - falling back to {LAKEHOUSE!r}.')",
             "    print('         Attach your Lakehouse (Explorer panel) as the default and re-run',",
             "          'if this is not the one holding the loaded tables.')",
             "print('Workspace:', workspace_id)",
             "print('Lakehouse:', LAKEHOUSE)"),
        md("## Create, configure, and publish"),
        code("from fabric.dataagent.client import create_data_agent",
             "",
             "agent = create_data_agent(data_agent_name=NAME, workspace_id=workspace_id)",
             "agent.update_settings(ai_instructions=AI_INSTRUCTIONS)",
             "print('Applied AI instructions.')",
             "",
             "ds = agent.add_staging_datasource(",
             "    artifact_name_or_id=LAKEHOUSE, workspace_id_or_name=workspace_id)",
             "print('Added datasource:', LAKEHOUSE)",
             "",
             "# datasource-level instructions (method name varies by SDK version)",
             "for _m in ('update_configuration', 'update_settings', 'set_instructions'):",
             "    _fn = getattr(ds, _m, None)",
             "    if callable(_fn) and DS_INSTRUCTIONS:",
             "        try:",
             "            _fn(instructions=DS_INSTRUCTIONS)",
             "            print('datasource instructions via', _m)",
             "            break",
             "        except Exception:",
             "            pass",
             "",
             "# example queries (best-effort across SDK versions)",
             "_added = False",
             "for _t in (ds, agent):",
             "    for _m in ('add_example_queries', 'add_example_query'):",
             "        _fn = getattr(_t, _m, None)",
             "        if not callable(_fn):",
             "            continue",
             "        try:",
             "            if _m.endswith('queries'):",
             "                _fn(EXAMPLE_QUERIES)",
             "            else:",
             "                for _q, _s in EXAMPLE_QUERIES:",
             "                    _fn(_q, _s)",
             "            print('example queries via', _m)",
             "            _added = True",
             "            break",
             "        except Exception:",
             "            pass",
             "    if _added:",
             "        break",
             "",
             "agent.publish_staging(description=DESCRIPTION)",
             "print('Published data agent.')"),
        md("## Data agent id + MCP endpoint"),
        code("aid = None",
             "for _a in ('id', 'artifact_id', 'data_agent_id'):",
             "    aid = getattr(agent, _a, None)",
             "    if aid:",
             "        break",
             "if aid:",
             "    print('DATA_AGENT_ARTIFACT_ID =', aid)",
             "    print('DATA_AGENT_MCP_ENDPOINT =',",
             "          f'https://api.fabric.microsoft.com/v1/mcp/workspaces/{workspace_id}/dataagents/{aid}/agent')",
             "    print('\\nAdd these to your local .env so the Foundry agents can bind to the data agent.')",
             "else:",
             "    print('Published. Copy the data agent id + MCP URL from the agent settings ->',",
             "          'Model Context Protocol tab into .env.')"),
    ])


if __name__ == "__main__":
    write("01_setup_lakehouse.ipynb", nb_01())
    write("02_load_bronze.ipynb", nb_02())
    write("03_build_silver_gold.ipynb", nb_03())
    write("04_ml_scores.ipynb", nb_04())
    write("05_create_data_agent.ipynb", nb_05())
    print("Done.")
