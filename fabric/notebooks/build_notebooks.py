"""
Builds the Fabric notebooks (.ipynb) for the medallion pipeline.

Keeping the notebook *source* here (plain Python) guarantees valid, reproducible
notebook JSON. Run this to (re)generate the .ipynb files, which are the portable
artifacts you upload to / run in Microsoft Fabric:

    python fabric/notebooks/build_notebooks.py

Notebooks produced:
    01_setup_lakehouse.ipynb      - validate lakehouse + landing files
    02_load_bronze.ipynb          - raw parquet -> bronze.* Delta tables (bronze schema)
    03_build_silver_gold.ipynb    - curated dim_/fact_ tables (clean names)
    04_ml_scores.ipynb            - trained churn model (MLflow) + cross-sell + customer_360
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

# Medallion schemas (Lakehouse must be schema-enabled). Silver is intentionally empty for now.
BRONZE, SILVER, GOLD = "bronze", "silver", "gold"
# Gold tables the Data Agent should be able to query.
GOLD_TABLES = CURATED + ["ml_churn_score", "ml_crosssell_reco", "customer_360"]


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
           "Confirms a schema-enabled Lakehouse is attached, creates the medallion **schemas**",
           "(`bronze`, `silver`, `gold`), and checks the landing Parquet files are present.",
           "Upload `data/parquet/*.parquet` to the Lakehouse **Files/landing/** folder first",
           "(the `10_provision_fabric.ps1` script does this automatically)."),
        md("## Create medallion schemas",
           "",
           "The Lakehouse must be **schema-enabled** (10_provision_fabric.ps1 creates it that way).",
           "`silver` is created but intentionally left empty for now."),
        code("for schema in ('bronze', 'silver', 'gold'):",
             "    spark.sql(f'CREATE SCHEMA IF NOT EXISTS {schema}')",
             "    print('schema ready:', schema)"),
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
           "Reads each raw Parquet file from `Files/landing/` and writes it as a Delta table",
           "in the **`bronze`** schema (`bronze.<table>`)."),
        code("LANDING = 'Files/landing'",
             f"tables = {TABLES!r}",
             "",
             "spark.sql('CREATE SCHEMA IF NOT EXISTS bronze')",
             "for t in tables:",
             "    df = spark.read.parquet(f'{LANDING}/{t}.parquet')",
             "    (df.write.format('delta').mode('overwrite')",
             "        .option('overwriteSchema', 'true').saveAsTable(f'bronze.{t}'))",
             "    print(f'bronze.{t:24s} {df.count():>8,} rows')"),
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
           "Promotes `bronze.*` to curated tables with clean business names in the **`gold`**",
           "schema (`gold.dim_*`, `gold.fact_*`) and casts date/timestamp columns for the SQL",
           "endpoint. The **`silver`** schema is created but left empty for now (the synthetic",
           "source is already clean, so no separate silver transformations are needed yet).",
           "ML tables and `customer_360` are built in notebook 04."),
        code("from pyspark.sql import functions as F",
             "",
             "spark.sql('CREATE SCHEMA IF NOT EXISTS silver')  # intentionally empty for now",
             "spark.sql('CREATE SCHEMA IF NOT EXISTS gold')",
             "",
             f"curated = {CURATED!r}",
             f"date_cols = {date_cols!r}",
             f"ts_cols = {ts_cols!r}",
             "",
             "for t in curated:",
             "    df = spark.table(f'bronze.{t}')",
             "    for c in date_cols.get(t, []):",
             "        if c in df.columns:",
             "            df = df.withColumn(c, F.to_date(F.col(c)))",
             "    for c in ts_cols.get(t, []):",
             "        if c in df.columns:",
             "            df = df.withColumn(c, F.to_timestamp(F.col(c)))",
             "    (df.write.format('delta').mode('overwrite')",
             "        .option('overwriteSchema', 'true').saveAsTable(f'gold.{t}'))",
             "    print(f'gold.{t:24s} {df.count():>8,} rows')"),
        code("print('Curated gold dim/fact tables built. silver schema is empty by design.')"),
    ])


# ----------------------------------------------------------------------------
# 04 - ML scores + customer_360
# ----------------------------------------------------------------------------
def nb_04():
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

    churn_feature_sql = """
SELECT
  a.account_id, a.customer_id,
  c.tenure_months,
  CAST(a.autopay AS INT) AS autopay,
  CASE a.credit_class WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END AS credit_risk,
  COALESCE(s.product_count, 0) AS product_count,
  COALESCE(s.total_mrc, 0.0) AS total_mrc,
  COALESCE(u.unpaid_ct, 0) AS unpaid_ct,
  COALESCE(sm.avg_uptime, 100.0) AS avg_uptime,
  COALESCE(sm.avg_latency, 20.0) AS avg_latency,
  COALESCE(fb.avg_csat, 5.0) AS avg_csat,
  COALESCE(ct.cancel_ct, 0) AS cancel_ct,
  a.churn_label
FROM dim_account a
JOIN dim_customer c ON a.customer_id = c.customer_id
LEFT JOIN (SELECT account_id, COUNT(*) AS product_count, SUM(mrc) AS total_mrc
           FROM fact_subscription WHERE status = 'active' GROUP BY account_id) s ON a.account_id = s.account_id
LEFT JOIN (SELECT account_id, COUNT(*) AS unpaid_ct FROM fact_invoice WHERE paid = false
           GROUP BY account_id) u ON a.account_id = u.account_id
LEFT JOIN (SELECT account_id, AVG(uptime_pct) AS avg_uptime, AVG(latency_ms) AS avg_latency
           FROM fact_service_metric GROUP BY account_id) sm ON a.account_id = sm.account_id
LEFT JOIN (SELECT account_id, AVG(csat) AS avg_csat FROM fact_feedback GROUP BY account_id) fb
           ON a.account_id = fb.account_id
LEFT JOIN (SELECT customer_id, COUNT(*) AS cancel_ct FROM fact_contact WHERE reason = 'cancel_request'
           GROUP BY customer_id) ct ON a.customer_id = ct.customer_id
""".strip()

    return notebook([
        md("# 04 - ML scores + Customer 360 (Gold)",
           "",
           "Computes churn risk and cross-sell recommendations from the curated tables,",
           "then builds the denormalized `customer_360` gold table used by the SQL endpoint",
           "and the Fabric Data Agent. All tables are read from / written to the **`gold`** schema."),
        md("## Use the gold schema",
           "",
           "Sets the current schema to `gold` so the statements below read the curated tables",
           "and create the ML + `customer_360` tables in `gold`."),
        code("spark.sql('CREATE SCHEMA IF NOT EXISTS gold')",
             "spark.sql('USE gold')",
             "print('current schema:', spark.catalog.currentDatabase())"),
        md("## Churn model (trained in Fabric with MLflow)",
           "",
           "Trains a scikit-learn classifier on `churn_label` (the observed-churn training",
           "target), logs it to an **MLflow experiment**, **registers it as a Fabric ML model**,",
           "then scores every account into `gold.ml_churn_score`. This replaces the old",
           "rule-based SQL scoring with a real train -> register -> score pipeline."),
        code("import mlflow",
             "import numpy as np",
             "import pandas as pd",
             "from sklearn.ensemble import GradientBoostingClassifier",
             "from sklearn.model_selection import train_test_split",
             "from sklearn.metrics import roc_auc_score",
             "",
             "FEATURES = ['tenure_months', 'autopay', 'credit_risk', 'product_count', 'total_mrc',",
             "            'unpaid_ct', 'avg_uptime', 'avg_latency', 'avg_csat', 'cancel_ct']",
             "feat = spark.sql('''" + churn_feature_sql + "''').toPandas()",
             "X = feat[FEATURES].astype('float64')",
             "y = feat['churn_label'].astype('int32')",
             "print('accounts:', len(feat), '| churn rate:', round(float(y.mean()), 3))"),
        code("mlflow.set_experiment('telco-churn')",
             "X_tr, X_te, y_tr, y_te = train_test_split(",
             "    X, y, test_size=0.25, random_state=42, stratify=y)",
             "with mlflow.start_run(run_name='churn-gbc'):",
             "    model = GradientBoostingClassifier(random_state=42)",
             "    model.fit(X_tr, y_tr)",
             "    auc = float(roc_auc_score(y_te, model.predict_proba(X_te)[:, 1]))",
             "    mlflow.log_param('model_type', 'GradientBoostingClassifier')",
             "    mlflow.log_metric('test_auc', auc)",
             "    mlflow.sklearn.log_model(model, artifact_path='model',",
             "                             registered_model_name='telco_churn_model')",
             "print('Registered telco_churn_model | test AUC:', round(auc, 3))"),
        code("# Score every account. Prefer the registered model (governance round-trip),",
             "# else fall back to the in-memory model just trained.",
             "proba = None",
             "try:",
             "    from mlflow.tracking import MlflowClient",
             "    _vs = MlflowClient().search_model_versions(\"name='telco_churn_model'\")",
             "    _v = max(_vs, key=lambda v: int(v.version)).version",
             "    scorer = mlflow.sklearn.load_model(f'models:/telco_churn_model/{_v}')",
             "    proba = scorer.predict_proba(X)[:, 1]",
             "    print('Scored with registered model version', _v)",
             "except Exception as ex:",
             "    print('registry load failed, scoring with in-memory model:', ex)",
             "    proba = model.predict_proba(X)[:, 1]",
             "feat['churn_probability'] = np.round(proba, 3)",
             "feat['risk_band'] = np.where(feat.churn_probability >= 0.55, 'High',",
             "                     np.where(feat.churn_probability >= 0.30, 'Medium', 'Low'))"),
        code("# Per-account top reason: standardized feature x model importance -> biggest risk driver.",
             "imp = dict(zip(FEATURES, model.feature_importances_))",
             "Z = (X - X.mean()) / X.std(ddof=0).replace(0, 1.0)",
             "risk_dir = {'tenure_months': -1, 'autopay': -1, 'credit_risk': 1, 'product_count': -1,",
             "            'total_mrc': 0, 'unpaid_ct': 1, 'avg_uptime': -1, 'avg_latency': 1,",
             "            'avg_csat': -1, 'cancel_ct': 1}",
             "labels = {'tenure_months': 'short tenure', 'autopay': 'no autopay', 'credit_risk': 'credit risk',",
             "          'unpaid_ct': 'unpaid invoices', 'avg_uptime': 'degraded service',",
             "          'avg_latency': 'high latency', 'avg_csat': 'low satisfaction',",
             "          'cancel_ct': 'cancellation intent', 'product_count': 'few products'}",
             "contrib = pd.DataFrame({f: Z[f] * risk_dir[f] * imp[f] for f in labels}, index=Z.index)",
             "feat['top_reason'] = contrib.idxmax(axis=1).map(labels)",
             "feat.loc[feat.risk_band == 'Low', 'top_reason'] = 'stable account'"),
        code("from pyspark.sql import functions as F",
             "score_df = spark.createDataFrame(",
             "    feat[['customer_id', 'account_id', 'churn_probability', 'risk_band', 'top_reason']])",
             "score_df = score_df.withColumn('scored_date', F.current_date())",
             "(score_df.write.format('delta').mode('overwrite')",
             "    .option('overwriteSchema', 'true').saveAsTable('gold.ml_churn_score'))",
             "print('gold.ml_churn_score rows:', score_df.count())",
             "spark.sql('SELECT risk_band, COUNT(*) c FROM gold.ml_churn_score GROUP BY risk_band ORDER BY 1').show()"),
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

    return notebook([
        md("# 05 - Create the Fabric Data Agent",
           "",
           "Run this **inside Fabric**. It creates the Telco data agent, applies the AI",
           "instructions, and attaches your Lakehouse as a data source. You then **select the",
           "gold-schema tables and Publish in the Data Agent UI**.",
           "",
           "**Steps:** attach your Lakehouse as the default Lakehouse, then **Run all**. Then finish",
           "in the UI (select tables + Publish) and copy the printed `DATA_AGENT_ARTIFACT_ID` and",
           "`DATA_AGENT_MCP_ENDPOINT` into your local `.env`.",
           "",
           "> This is the supported way to create the data agent (it is not created from the local",
           "> workstation). Config below mirrors `fabric/data-agent/config.yaml`, the source of truth."),
        code("%pip install --quiet fabric-data-agent-sdk"),
        md("## Configuration (mirrors fabric/data-agent/config.yaml)"),
        code(f"NAME = {cfg['name']!r}",
             f"DESCRIPTION = {cfg.get('description', 'Telco data agent')!r}",
             f"LAKEHOUSE_DEFAULT = {ds.get('artifact', 'TelcoLakehouse')!r}  # fallback only",
             f"AI_INSTRUCTIONS = {cfg['ai_instructions']!r}"),
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
        md("## Create the agent + attach the Lakehouse",
           "",
           "Creates the data agent, applies the AI instructions, and attaches your Lakehouse as a",
           "data source. **Table selection and publishing are done in the Data Agent UI** (next",
           "step) - programmatic table selection isn't reliable across SDK versions."),
        code("import warnings",
             "warnings.simplefilter('ignore', FutureWarning)",
             "from fabric.dataagent.client import create_data_agent",
             "",
             "agent = create_data_agent(data_agent_name=NAME, workspace_id=workspace_id)",
             "agent.update_settings(ai_instructions=AI_INSTRUCTIONS)",
             "print('Applied AI instructions.')",
             "",
             "agent.add_staging_datasource(",
             "    artifact_name_or_id=LAKEHOUSE, workspace_id_or_name=workspace_id)",
             "print('Attached Lakehouse datasource:', LAKEHOUSE)"),
        md("## Finish in the Data Agent UI",
           "",
           "1. Open the **TelcoCustomerServiceAgent** data agent in your workspace.",
           "2. In the datasource, **select the `gold`-schema tables** you want it to query",
           "   (check the `gold` schema to include all of them).",
           "3. (Optional) add example queries from `fabric/data-agent/config.yaml`.",
           "4. Click **Publish**.",
           "",
           "The MCP endpoint printed below works once the agent is published."),
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
             "    print('\\nAfter you select tables + Publish in the UI, add these to your local .env.')",
             "else:",
             "    print('Agent created. After selecting tables + publishing in the UI, copy the')",
             "    print('data agent id + MCP URL from the agent settings -> Model Context Protocol tab.')"),
    ])


if __name__ == "__main__":
    write("01_setup_lakehouse.ipynb", nb_01())
    write("02_load_bronze.ipynb", nb_02())
    write("03_build_silver_gold.ipynb", nb_03())
    write("04_ml_scores.ipynb", nb_04())
    write("05_create_data_agent.ipynb", nb_05())
    print("Done.")
