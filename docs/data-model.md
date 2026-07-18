# Data Model

The synthetic dataset models a residential telecommunications provider offering **internet, mobile, and voice** products. Data is generated locally (see [`../data-generation/`](../data-generation)) and loaded into a Fabric Lakehouse using a Bronze/Silver/Gold medallion.

## Entity overview

```mermaid
erDiagram
    dim_customer ||--o{ dim_account : has
    dim_account  ||--o{ fact_subscription : holds
    dim_account  ||--o{ fact_invoice : billed
    fact_invoice ||--o{ fact_invoice_line : contains
    dim_product  ||--o{ fact_subscription : sold_as
    dim_plan     ||--o{ dim_product : packaged_in
    dim_device   ||--o{ fact_subscription : uses
    dim_promotion||--o{ fact_offer : instance_of
    dim_account  ||--o{ fact_offer : targeted
    dim_customer ||--o{ fact_contact : contacted
    dim_account  ||--o{ fact_usage_data : consumes
    dim_account  ||--o{ fact_usage_voice : consumes
    dim_geography||--o{ dim_customer : located_in
    dim_geography||--o{ fact_coverage : covers
    dim_geography||--o{ fact_outage : affected_by
    dim_account  ||--o{ fact_work_order : requested
    fact_work_order ||--o{ fact_appointment : scheduled
    dim_account  ||--o{ fact_feedback : gave
    dim_customer ||--o{ ml_churn_score : scored
    dim_account  ||--o{ ml_crosssell_reco : recommended
```

## Tables

### Dimensions

| Table | Grain | Key columns |
|---|---|---|
| `dim_customer` | one row per customer | `customer_id`, name, dob, segment, tenure_months, contact prefs, `geo_id` |
| `dim_account` | one billing account | `account_id`, `customer_id`, status (active/suspended/cancelled), open_date, autopay |
| `dim_geography` | one ZIP/region | `geo_id`, zip, city, state, region, lat/lon |
| `dim_product` | one sellable product | `product_id`, name, category (internet/mobile/voice/tv), monthly_price |
| `dim_plan` | one plan/tier | `plan_id`, name, speed_mbps or data_gb, price, `product_id` |
| `dim_device` | one device | `device_id`, model, type (modem/phone/router), monthly_price |
| `dim_promotion` | one promo template | `promotion_id`, name, type (retention/acquisition/crosssell), discount, terms |

### Facts

| Table | Grain | Notes |
|---|---|---|
| `fact_subscription` | customer's product instance | `subscription_id`, `account_id`, `product_id`, `plan_id`, `device_id`, start/end, mrc |
| `fact_invoice` | one monthly invoice | `invoice_id`, `account_id`, period, amount, due_date, paid, **`is_first_bill`** |
| `fact_invoice_line` | one charge line | `invoice_id`, description, amount, category (recurring/usage/one-time/credit) |
| `fact_offer` | offer presented to account | `offer_id`, `account_id`, `promotion_id`, presented_date, status (offered/accepted/declined) |
| `fact_contact` | one interaction | `contact_id`, `customer_id`, channel (web/ivr/agent/chat), reason, timestamp, `handoff` flag |
| `fact_usage_data` | daily data usage | `account_id`, date, gb_used |
| `fact_usage_voice` | daily voice usage | `account_id`, date, minutes |
| `fact_coverage` | speed available by ZIP | `geo_id`, technology, max_down_mbps, max_up_mbps |
| `fact_outage` | outage event | `outage_id`, `geo_id`, start, end, severity, resolved |
| `fact_service_metric` | daily service KPI | `account_id`, date, latency_ms, packet_loss_pct, uptime_pct |
| `fact_work_order` | ticket / truck-roll | `work_order_id`, `account_id`, type, opened, closed, status, resolution |
| `fact_appointment` | scheduled visit | `appointment_id`, `work_order_id`, window_start, window_end, status |
| `fact_feedback` | survey response | `feedback_id`, `account_id`, csat (1-5), nps (0-10), comment, date |

### ML outputs (Gold)

| Table | Notes |
|---|---|
| `ml_churn_score` | `customer_id`, churn_probability, risk_band, top_reason (rule-based/synthetic) |
| `ml_crosssell_reco` | `account_id`, recommended_product_id, score, rationale |

### Gold serving object

| Object | Purpose |
|---|---|
| `customer_360` | Denormalized per-customer profile: identity, account status, active subscriptions, current balance / first-bill flag, recent contacts, open work orders, outage exposure, churn risk, top cross-sell — the single object the Web App fetches via the SQL endpoint |

## Journey → data mapping

| Journey | Primary tables |
|---|---|
| **1. Acquisition + handoff → cross-sell** | `dim_customer`, `fact_subscription`, `dim_product`, `ml_crosssell_reco`, `fact_offer`, `fact_contact` (handoff) |
| **2. First-bill support** | `fact_invoice` (`is_first_bill`), `fact_invoice_line`, `fact_subscription`, `dim_plan` |
| **3. Service degradation & retention** | `fact_outage`, `fact_service_metric`, `fact_work_order`, `ml_churn_score`, `dim_promotion`/`fact_offer` (credit/save) |

## Generation principles

- **Deterministic**: a fixed seed (`DATA_SEED`) makes every run reproducible.
- **Referentially consistent**: child rows only reference existing parents.
- **Realistic distributions**: tenure, usage, churn risk, and first-bill timing follow plausible shapes so the demo journeys have signal.
- **Small by default**: ~1,000 customers keeps committed files tiny; scale with `--customers`.

Output is written to `data/csv/` (readable, diff-friendly) and `data/parquet/` (load-ready).
