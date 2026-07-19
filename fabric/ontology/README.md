# Ontology

[`ontology.yaml`](ontology.yaml) is the shared **business vocabulary** for the solution. It
maps natural-language terms (subscriber, first bill, at-risk, cross-sell candidate, degraded
service) to the underlying tables, columns, and metrics.

## Why it matters

- Gives the **Fabric Data Agent** and **Foundry agents** consistent language so they resolve
  ambiguous questions the same way ("first bill" always means `fact_invoice.is_first_bill = true`).
- Documents entities, synonyms, canonical metrics, and per-journey signals in one place.

## How it's used

1. **Data Agent instructions** — the glossary and entity map inform
   [`../data-agent/config.yaml`](../data-agent/config.yaml) `ai_instructions` (**active** — this
   is how the ontology grounds agents today).
2. **Foundry agent grounding** — journey agents reference the same terms/signals.
3. **Native Fabric Ontology item (deployable)** — Fabric IQ now has a native **Ontology
   (preview)** item that you can **generate directly from the semantic model** we build in
   notebook 06. `ontology.yaml` is the design spec/checklist for that item.

## Deploying the native Fabric IQ Ontology (preview)

Because notebook 06 creates a **Direct Lake** semantic model, generating the ontology from it
produces entity types, **properties + live data bindings**, and relationships automatically
(Direct Lake is the mode that binds data — Import mode only generates the shape).

**Steps:**
1. Run `fabric/notebooks/06_create_semantic_model.ipynb` to create the `TelcoCustomerService`
   semantic model over the gold tables (relationships + measures included).
2. In Fabric, open the semantic model (or its overview page) and choose **Generate Ontology**
   from the ribbon. Name it `TelcoCustomerServiceOntology` (letters/numbers/underscores only)
   and **Create**.
3. Fabric creates entity types matching the gold tables (Customer, Account, Invoice, Outage,
   WorkOrder, …), their properties/bindings, and relationships from the model.
4. Finish manually (per Fabric IQ guidance): confirm each entity's **key**, bind any
   **time-series** properties (e.g. `fact_usage_data`, `fact_service_metric`), and verify
   relationship bindings. Use `ontology.yaml` as the checklist (entities, keys, synonyms,
   journey signals).

**Prerequisites / gotchas:**
- Tenant **preview** settings for Ontology (Fabric IQ) must be enabled (admin toggle).
- Direct Lake **data bindings** populate only when the backing Lakehouse's workspace has
  **inbound public access enabled**; relationship bindings require an identified primary key.
- Ontology supports **managed** Lakehouse tables only (ours are managed), and doesn't support
  `Decimal`-typed columns (our numerics are float/double, so this is fine).

> The Create Ontology REST API exists, but the *generate-from-semantic-model* operation is
> portal-first in preview, so we drive it from the portal and keep `ontology.yaml` as the
> reproducible source of truth.

## Structure

| Section | Contents |
|---|---|
| `entities` | Business objects → table, key, synonyms, key attributes, states |
| `metrics` | Canonical metric definitions (aligned to the semantic model measures) |
| `glossary` | Term → precise data-model meaning (disambiguation) |
| `journeys` | Which entities + signals drive each of the three demo journeys |

Keep this file in sync with `../semantic-model/model_spec.yaml` and the Lakehouse gold tables.
