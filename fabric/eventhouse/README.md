# Real-Time Intelligence (Eventhouse / KQL)

An **Eventhouse** (`telco_realtime`) with a KQL database holding **two customer-keyed real-time
tables**. It complements the Lakehouse batch data with a real-time store the ontology can bind
to, so the ontology-backed Data Agent can answer relationship questions over live-style data.

| Table | What | Keyed by |
|---|---|---|
| `OutageEvents` | Outage information experienced by a customer | `customer_id` |
| `WebSessions` | Web browser session (clickstream summary) per customer | `customer_id` |

Both are keyed by `customer_id` (`CUST######`) from `data/csv/dim_customer.csv`, so they line up
with the Lakehouse data. Event timestamps anchor to the dataset date **2026-06-30**.

## Table schemas

All column types are chosen to be **Fabric IQ ontology-binding compatible**:
`string` (ids/categoricals), `datetime` (timestamps), `real` (continuous → ontology **Double**),
`long` (counts), `bool` (flags). **No `decimal`** (ontology returns null for Decimal), no
`dynamic`/`timespan`/`guid`.

### `OutageEvents`
| Column | KQL type | Notes |
|---|---|---|
| `event_id` | string | key (`OEV############`) |
| `customer_id` | string | → Customer |
| `geo_id` | string | → Geography |
| `event_time` | datetime | when the outage began affecting the customer |
| `outage_type` | string | Fiber cut / Power loss / Equipment failure / Weather / Congestion |
| `severity` | string | Minor / Major / Critical |
| `status` | string | Detected / Investigating / Restoring / Resolved |
| `affected_service` | string | Internet / Mobile / Voice / TV (from the customer's products) |
| `duration_minutes` | real | outage duration |
| `restored_time` | datetime | null while ongoing |
| `reported_by_customer` | bool | did the customer report it |

### `WebSessions`
| Column | KQL type | Notes |
|---|---|---|
| `session_id` | string | key (`WSN############`) |
| `customer_id` | string | → Customer |
| `session_start` / `session_end` | datetime | session window |
| `duration_seconds` | real | |
| `device_type` | string | Desktop / Mobile / Tablet |
| `browser` | string | Chrome / Edge / Safari / Firefox |
| `os` | string | Windows / macOS / iOS / Android |
| `entry_page` / `exit_page` | string | `/home`, `/billing`, `/support`, `/plans`, `/outage-status`, … |
| `page_views` | long | pages viewed in the session |
| `referrer` | string | Direct / Search / Email / Social / Ad |
| `authenticated` | bool | signed in |
| `converted` | bool | completed an action (paid bill / started chat / bought add-on) |

## 1. Generate the data (local, reads the committed customers)

```powershell
# reads data/csv/dim_customer.csv (+ geography/outage/subscription) and writes data/kql/*.csv
python ./data-generation/generate_realtime.py
# optional: --seed 7  --as-of 2026-06-30
```

Output: `data/kql/outage_events.csv`, `data/kql/web_sessions.csv`, `data/kql/manifest.json`
(committed to the repo). Default volumes ≈ **380 outage rows** and **1,870 session rows** for the
1000-customer sample. Volume knobs live in `generate_realtime.py` (`CONFIG`).

## 2. Provision the Eventhouse + load the data

```powershell
./scripts/30_provision_eventhouse.ps1        # -SkipIngest to only (re)create tables
```

This creates (or reuses) the `telco_realtime` Eventhouse + KQL database, creates the two tables,
and ingests the CSVs via chunked `.ingest inline`. It writes `KQL_DATABASE_NAME` and
`KQL_QUERY_URI` to `.env`. Re-running clears + re-ingests (idempotent, no duplicates).

> **Capacity note:** the Eventhouse needs the workspace's Fabric **capacity running**. If it's
> paused you'll see `CapacityNotActive` — resume it (Azure portal or
> `az resource invoke-action --action resume --ids <capacity-resource-id>`) and re-run.

### Verify

```powershell
# quick counts (uses the Kusto helpers in scripts/lib/Common.psm1)
Import-Module ./scripts/lib/Common.psm1 -Force
$e = Import-DotEnv; $tok = Get-KustoToken -UseSpn -Resource $e.KQL_QUERY_URI
Invoke-KustoMgmt -QueryUri $e.KQL_QUERY_URI -Database $e.KQL_DATABASE_NAME -Token $tok `
  -Csl 'OutageEvents | count' -Query
```

## 3. Bind into the ontology (manual — done in Fabric IQ)

Connect these tables to the existing `TelcoOntology`. There are **two valid ways** to bind a
KQL table, and they're queried very differently — pick based on how you want the Data Agent to
reason about the data.

### Model A — separate entity type (discrete, countable events)

Bind each KQL table as its **own entity type** (one row = one entity instance) and relate it to
`Customer`/`Geography`. Best when you want to **count/list/traverse** events
("how many outages did this customer have?", "list their sessions").

| Entity type | Bound KQL table | Key |
|---|---|---|
| `OutageEvent` | `OutageEvents` | `event_id` |
| `WebSession` | `WebSessions` | `session_id` |

Suggested relationships (the **mapping table** is the KQL table itself — it holds both keys):

| Relationship | From → To | Mapping table | from_key → to_key |
|---|---|---|---|
| `customer_has_outage_event` | Customer → OutageEvent | `OutageEvents` | customer_id → event_id |
| `outage_event_in_geography` | OutageEvent → Geography | `OutageEvents` | event_id → geo_id* |
| `customer_has_web_session` | Customer → WebSession | `WebSessions` | customer_id → session_id |

\* the mapping table carries `geo_id`, so bind Geography's side to that column.

Query it by **traversing the graph** (GQL):

```gql
MATCH (c:Customer)-[:customer_has_outage_event]->(o:OutageEvent)
WHERE c.customer_id == "CUST000005"
RETURN c.customer_id, o.event_id, o.event_time, o.outage_type, o.severity, o.affected_service
ORDER BY o.event_time ASC
```

### Model B — time-series binding on the Customer entity (temporal signals)

Add the KQL table as a **second binding on the existing `Customer` entity** (not a new entity):
entity key `customer_id → customer_id`, **timestamp column** `event_time` (or `session_start`),
and the remaining columns become **time-varying properties of Customer**. Best for
**signals over time** attached to the customer. In this model there is **no `OutageEvent`
node** — you don't traverse to a child; the data is properties *of* Customer.

Verify a time-series binding:
1. **Customer → View entity type details → Configure → Manage property bindings** — you should see
   **two bindings** (the static Lakehouse `dim_customer` one + the Eventhouse time-series one),
   with the outage/session columns bound and the key mapping `customer_id → customer_id`. That
   binding *is* the connection to Customer.
2. **Explore** experience → select a Customer instance (e.g. `CUST000005`) → view its time-series
   properties over time (CUST000005 has two outage points: 2026-06-28 and 2026-05-09).
3. Ask `TelcoOntologyDataAgent`: *"What outages has customer CUST000005 experienced and when?"* —
   it reads the time-series properties off Customer (no graph traversal).

> Rule of thumb: **Model A** for discrete events you count/list/traverse; **Model B** for
> time-series signals you trend per customer. You can even do both (e.g. entity for outages,
> time-series for sessions).

> See [`../ontology/README.md`](../ontology/README.md) for the relationship mapping-table rule.

## Notes

- Inline ingest keeps this self-contained for the demo's modest volumes. For larger loads,
  switch to blob/OneLake ingest or an Eventstream/pipeline.
- The data is a **seeded historical+recent batch** into the KQL store (not a live stream);
  timestamps cluster toward the anchor date to give a "recent activity" feel.
