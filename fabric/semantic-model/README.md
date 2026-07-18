# Semantic Model

A **Direct Lake** semantic model over the Telco Lakehouse gold tables. It gives Power BI
reports and the Fabric Data Agent a business-friendly layer (friendly names, relationships,
and reusable measures).

## Source of truth

[`model_spec.yaml`](model_spec.yaml) declares the tables, relationships, and DAX measures.
It is tool-agnostic — you can apply it three ways:

1. **Scripted (recommended):** `python create_semantic_model.py`
   Uses [semantic-link-labs](https://github.com/microsoft/semantic-link-labs) to create the
   Direct Lake model and add relationships + measures. Run it in a Fabric notebook, or from a
   machine authenticated to Fabric (Azure CLI / service principal).
   ```powershell
   ./.venv/Scripts/pip install semantic-link-labs
   ./.venv/Scripts/python fabric/semantic-model/create_semantic_model.py
   ```
2. **Portal:** in the Lakehouse, choose **New semantic model**, pick the gold tables, then add
   the relationships and measures from `model_spec.yaml`.
3. **Tabular Editor:** create the model, then paste the measures from `model_spec.yaml`.

## Measures

| Measure | Purpose |
|---|---|
| Customer Count / Active Accounts / Suspended Accounts | population + status |
| Monthly Recurring Revenue | active subscription MRC |
| Total Billed / Open Balance / First Bill Count | billing + first-bill journey |
| High Risk Customers / Avg Churn Probability | retention journey |
| Avg Uptime Pct | service-degradation journey |
| Avg CSAT / Offer Acceptance Rate | experience + offers |

## Notes

- Direct Lake reads Delta tables directly from OneLake — no import/refresh — so the model
  reflects the latest notebook run.
- The `sempy_labs` API evolves; `create_semantic_model.py` wraps optional calls so a version
  mismatch degrades gracefully. If scripting fails, fall back to the portal using
  `model_spec.yaml` as the checklist.
