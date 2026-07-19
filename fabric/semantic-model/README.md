# Semantic Model

A **Direct Lake** semantic model over the Telco Lakehouse gold tables. It gives Power BI
reports and the Fabric Data Agent a business-friendly layer (friendly names, relationships,
and reusable measures).

## Source of truth

[`model_spec.yaml`](model_spec.yaml) declares the tables, relationships, and DAX measures.
It is tool-agnostic — you can apply it three ways:

1. **Fabric notebook (recommended):** run `fabric/notebooks/06_create_semantic_model.ipynb`
   in Fabric (attach your Lakehouse, **Run all**). It's generated from this spec by
   `build_notebooks.py` and uses `semantic-link-labs` to create the Direct Lake model and
   add the relationships + measures. This is the reproducible path (the SDK can't run on a
   local Windows-on-Arm workstation, so it runs in Fabric like the data-agent notebook).
2. **Script:** `python create_semantic_model.py` (same logic, for a machine authenticated to
   Fabric via Azure CLI / a service principal).
3. **Portal / Tabular Editor:** create the model from the gold tables, then add the
   relationships and measures from `model_spec.yaml` as a checklist.

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
