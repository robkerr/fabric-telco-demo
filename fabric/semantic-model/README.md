# Semantic Model

A **Direct Lake** semantic model over the Telco Lakehouse gold tables. It gives Power BI
reports, the Fabric Data Agent, and the Fabric IQ Ontology a business-friendly layer (friendly
names, relationships, and reusable measures).

> In this demo the model was created **manually in the Fabric portal** (see below).
> [`model_spec.yaml`](model_spec.yaml) is kept as the declarative **specification** of the
> tables, relationships, and measures — a checklist for reproducing the model, and the basis
> for a future scripted build.

## How it was created (manual, portal)

1. In the Fabric workspace, open the **Lakehouse** (`lh_telco`).
2. Use **New semantic model** (the Lakehouse "bootstrap" button), name it
   `TelcoCustomerService`, and select the **gold** tables listed in
   [`model_spec.yaml`](model_spec.yaml) (`tables:` section).
3. Open the new model and add the **relationships** and **DAX measures** from
   `model_spec.yaml`. You can do this in the model's web editor or with
   [Tabular Editor](https://tabulareditor.com/). `model_spec.yaml` lists every relationship
   (`from` → `to`) and measure (name, table, DAX expression, format string).
4. Direct Lake reads Delta directly from OneLake (no import/refresh), so the model always
   reflects the latest notebook run.

The model is the source for generating the **Fabric IQ Ontology** — see
[`../ontology/README.md`](../ontology/README.md).

## Measures (defined in `model_spec.yaml`)

| Measure | Purpose |
|---|---|
| Customer Count / Active Accounts / Suspended Accounts | population + status |
| Monthly Recurring Revenue | active subscription MRC |
| Total Billed / Open Balance / First Bill Count | billing + first-bill journey |
| High Risk Customers / Avg Churn Probability | retention journey |
| Avg Uptime Pct | service-degradation journey |
| Avg CSAT / Offer Acceptance Rate | experience + offers |

## Future: scripting the model

`model_spec.yaml` is intentionally tool-agnostic so the model can later be created
programmatically (e.g. with `semantic-link-labs` in a Fabric notebook). A scripted build was
prototyped but the portal path proved simpler and more reliable for this demo, so the script
was removed to keep the repo clean — the spec remains the reproducible source of truth.
