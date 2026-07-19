# Ontology (Fabric IQ)

The **`TelcoOntology`** item is a Fabric IQ **Ontology (preview)** graph over the gold tables.
It lets the Fabric Data Agent (`TelcoOntologyDataAgent`) answer *relationship* questions by
traversing entities with GQL — e.g. "what coverage is available in this customer's area?",
"which subscriptions are on this account?", "what work orders and appointments does this
account have?".

[`ontology.yaml`](ontology.yaml) mirrors the live item (entities, keys, relationships,
glossary, journeys). It's the design spec and the basis for future scripted recreation.

## How it was created (manual, portal)

The ontology was authored by hand in the Fabric portal. Two ways to start:

- **Generate from the semantic model** — open the `TelcoCustomerService` semantic model and
  choose **Generate Ontology** from the ribbon. Fabric seeds entity types + properties +
  relationships from the model, which you then refine.
- **Build from OneLake** — create an Ontology item and add entity types by binding directly to
  gold Lakehouse tables.

Then define the entity types and relationships below, using `ontology.yaml` as the checklist.

### Prerequisites
- Tenant **Fabric IQ / Ontology (preview)** settings enabled (admin).
- Direct Lake **data bindings** populate only when the Lakehouse workspace has **inbound public
  access enabled**; each entity needs a **key** identified for relationship bindings to work.
- Ontology supports **managed** Lakehouse tables only; `Decimal`-typed columns aren't supported
  (our numerics are float/double, so that's fine).

## Entity types (11)

Each entity binds to one gold table and has a key:

| Entity | Gold table | Key |
|---|---|---|
| Customer | `dim_customer` | `customer_id` |
| Account | `dim_account` | `account_id` |
| Geography | `dim_geography` | `geo_id` |
| Coverage | `fact_coverage` | `coverage_id` |
| Product | `dim_product` | `product_id` |
| Plan | `dim_plan` | `plan_id` |
| Subscription | `fact_subscription` | `subscription_id` |
| Invoice | `fact_invoice` | `invoice_id` |
| WorkOrder | `fact_work_order` | `work_order_id` |
| Appointment | `fact_appointment` | `appointment_id` |
| Contact | `fact_contact` | `contact_id` |

## Relationship types (10)

| Relationship | From → To | Mapping table | from_key → to_key |
|---|---|---|---|
| customer_owns_account | Customer → Account | `dim_account` | customer_id → account_id |
| customer_has_location | Customer → Geography | `dim_customer` | customer_id → geo_id |
| account_has_subscription | Account → Subscription | `fact_subscription` | account_id → subscription_id |
| subscription_for_product | Subscription → Product | `fact_subscription` | subscription_id → product_id |
| subscription_has_plan | Subscription → Plan | `fact_subscription` | subscription_id → plan_id |
| account_has_invoice | Account → Invoice | `fact_invoice` | account_id → invoice_id |
| account_has_workorder | Account → WorkOrder | `fact_work_order` | account_id → work_order_id |
| workorder_has_appointment | WorkOrder → Appointment | `fact_appointment` | work_order_id → appointment_id |
| geo_has_coverage | Geography → Coverage | `fact_coverage` | geo_id → coverage_id |
| customer_is_contacted | Account → Contact | `fact_contact` | customer_id → contact_id* |

\* `fact_contact` carries `customer_id` (not `account_id`) — this edge is a candidate to
re-scope as **Customer → Contact**.

## How to author a relationship (the key gotcha)

A relationship needs a **mapping (edge) table**: one row per relationship instance that
contains **both** the source key **and** the target key. This is almost always the **fact /
"many"-side** table — **not** the source dimension.

Example — `geo_has_coverage` (Geography → Coverage):
- **Origin/source entity** = Geography (key `geo_id`)
- **Target entity** = Coverage (key `coverage_id`)
- **Mapping table** = **`fact_coverage`** (it has both `geo_id` and `coverage_id`) — *not*
  `dim_geography`, which has no `coverage_id`.
- **Matched Geography: geo_id** → `geo_id`; **Matched Coverage: coverage_id** → `coverage_id`.

> The portal mixes the terms "source" and "origin" (same thing = the *from* side). The middle
> **Mapping table** is the edge table, and it defaults to the origin's own dimension — which is
> the trap. Always set it to the table holding **both** keys.

## Syncing this file from Fabric

If you change the ontology in Fabric, pull the definition back:

```powershell
./scripts/export_ontology.ps1 -OntologyName TelcoOntology
```

This decodes the Fabric REST `getDefinition` parts into `fabric/ontology/_fabric_export/`
(git-ignored). Use it to update `ontology.yaml` to match.

## Also used as agent grounding

The glossary/entity map in `ontology.yaml` also informs the Data Agent AI instructions in
[`../data-agent/config.yaml`](../data-agent/config.yaml), so terms like "first bill" resolve
consistently.
