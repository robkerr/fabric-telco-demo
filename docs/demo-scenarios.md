# Demo Scenarios

Three scripted walkthroughs, one per customer journey. Each uses **real customer IDs** from the
default synthetic dataset (`--customers 1000`, `--seed 42`). If you regenerate with a different
seed/size, pick equivalent customers with the queries shown.

> Run the web app locally first (`app/README.md`) — it works in **local mode** with no cloud, so
> you can demo the Customer 360 + chat flow immediately. With the Fabric + Foundry pieces
> deployed, the same flow uses live data and the journey agents.

Reference date of the dataset ("today"): **2026-06-30**.

---

## Journey 1 — Acquisition + mid-journey handoff → cross-sell

**Customer:** `CUST000730` — Katelyn Jackson (active internet customer, no mobile).

**Story:** Katelyn started on the website, then was handed to a live agent. The agent's desktop
hydrates her 360 profile and surfaces a **cross-sell** opportunity.

**Steps**
1. In the Agent Desktop, search `CUST000730` and open the profile.
2. Note the **Cross-sell** alert: recommended **PROD_MOB** (mobile), score ~**0.89**.
3. Ask the assistant:
   - "What products does this customer already have?"
   - "What's the best add-on for this customer and what's the offer?"

**Expected (data-grounded):** internet-only today; recommend **Mobile** with **"Add Mobile,
Save $10/mo"** (`PROMO_XSELL_1`). Product literature comes from `foundry/knowledge/mobile-and-bundles.md`.

**Exercises:** `fact_subscription`, `ml_crosssell_reco`, `dim_promotion`, `fact_contact.handoff_to_agent`,
telco-CrossSellAgent + AI Search/Web IQ.

---

## Journey 2 — First-bill support

**Customer:** `CUST000003` — Joshua Stephens (new customer, unpaid first bill ≈ **$156.55**).

**Story:** Joshua calls confused that his first bill is higher than the advertised monthly rate.

**Steps**
1. Search `CUST000003` and open the profile.
2. Note the **Unpaid FIRST bill** alert (activation + proration).
3. Ask the assistant:
   - "Why is my first bill higher than my monthly rate?"
   - "Break down the charges on my first bill."

**Expected (data-grounded):** explains the recurring service charges **plus** the one-time
**$35 activation fee** and a **partial-month proration** line — the reason the first bill is high.
Cites the invoice amount and due date.

**Exercises:** `fact_invoice` (`is_first_bill`), `fact_invoice_line`, `fact_subscription`,
telco-BillingFirstBillAgent.

**Handy query (find your own example):**
```sql
SELECT customer_id, first_name, last_name, last_invoice_amount
FROM gold.customer_360
WHERE last_invoice_is_first_bill = true AND last_invoice_paid = false;
```

---

## Journey 3 — Service degradation & retention

**Customer:** `CUST000783` — Jennifer Blevins (active, **high churn risk ≈ 0.92**, recent outage in her area).

**Story:** Jennifer reports slow/unreliable service and hints at leaving. The agent sees she's in an
area with a **recent outage** and is **high churn risk**, and offers a save.

**Steps**
1. Search `CUST000783` and open the profile.
2. Note the **High churn risk** and **Recent outage in customer area** alerts.
3. Ask the assistant:
   - "Was there a recent outage in this customer's area?"
   - "How has this customer's service quality been recently?"
   - "This customer is thinking about cancelling — what can I offer?"

**Expected (data-grounded):** confirms a recent outage in her geography and degraded service
metrics (higher latency / lower uptime); recommends a **Service Outage Credit** (`PROMO_SVC_1`)
and/or a **Loyalty Credit** (`PROMO_RET_1`) / **20% off 6 months** (`PROMO_RET_2`).

**Exercises:** `fact_outage`, `fact_service_metric`, `ml_churn_score`, `dim_promotion`/`fact_offer`,
telco-ServiceRetentionAgent + Web IQ (weather).

---

## Running against live Fabric + Foundry

After completing Phases 1–3, set the app to live mode by providing `FABRIC_SQL_ENDPOINT`,
`FABRIC_LAKEHOUSE_NAME`, and `FOUNDRY_PROJECT_ENDPOINT` (plus the deployed
`foundry/agents.generated.json`). The Customer 360 panel then reads from the Fabric SQL endpoint,
and chat is routed by the app to the matching journey agent, which grounds its answer in the
Fabric Data Agent. See [`setup-guide.md`](setup-guide.md).
