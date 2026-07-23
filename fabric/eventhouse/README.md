# Real-Time Intelligence (Eventhouse / KQL)

An **Eventhouse** (`telco_realtime`) with a KQL database holding **real-time tables** the Fabric
IQ ontology binds to, so the ontology-backed Data Agent can answer live questions.

| Table | What | Keyed by | Recommended ontology binding |
|---|---|---|---|
| **`DeviceMetrics`** ⭐ | Per-device utilization / up-down telemetry over time | `device_id`, `account_id` | **time-series** on a `Device` entity (real-time) |
| `OutageEvents` | Outage information experienced by a customer | `customer_id`, `account_id` | entity or time-series (see below) |
| `WebSessions` | Web browser session (clickstream summary) per customer | `customer_id` | entity or time-series |

> **`DeviceMetrics` is the recommended real-time model.** It's designed for the *time-series
> binding* — a live feed queried straight from KQL at query time (no graph refresh) — attached
> to a stable **`Device`** entity. That combination is what makes the ontology Data Agent answer
> real-time questions like *"plot utilization by day for the last month for account 123's cable
> modem"* without confusion. See **[Recommended: Device + DeviceMetrics](#recommended-device--devicemetrics-real-time)**.

Timestamps anchor to the dataset date **2026-06-30** (except live-streamed rows, which use `now()`).

## Recommended: Device + DeviceMetrics (real-time)

Two ontology bindings work together:

1. **`Device` entity — static binding** to the gold Lakehouse table **`dim_customer_device`**
   (one physical modem/router per internet account). This gives stable, traversable device
   instances. Key = `device_id`. Relationship **`account_has_device`** (Account → Device,
   mapping table `dim_customer_device`, `account_id → device_id`).
2. **`DeviceMetrics` — time-series binding** on that same `Device` entity, from the Eventhouse
   (`device_id` key, `reading_time` timestamp). The metric columns (`utilization_pct`,
   `is_online`, `downstream_mbps`, `upstream_mbps`, `latency_ms`) become **live** time-series
   properties — queried from KQL at query time, so new readings appear instantly.

**Why this beats binding events straight onto Account:** a *static* entity binding is
materialized into the graph and only refreshes on a graph refresh (batch). A *time-series*
binding is **live-queried** — that's the only true real-time path, and it needs the `datetime`
column. The `Device` entity gives the agent something clean to traverse to (`Account → Device`);
the telemetry gives it live values to aggregate over time.

### Agent guidance (paste into `TelcoOntologyDataAgent`)

**AI instructions:**
> Device telemetry (utilization, up/down state, throughput, latency) is real-time time-series
> data on the **Device** entity, reached via `Account -[account_has_device]-> Device` (fed by the
> DeviceMetrics Eventhouse table; timestamp = `reading_time`). For "utilization/usage/online/
> latency/throughput over time" questions, aggregate these time-series properties by time window
> (e.g., `bin(reading_time, 1d)`). Do NOT use WorkOrder (repair tickets) or Invoice for device or
> connectivity questions.

**Example queries** (the strongest steer — add these question→GQL pairs):
- *"Plot utilization by day for the last month for account ACCT000193's cable modem"*
- *"Is account ACCT000193's device online right now, and what's its current utilization?"*
- *"What's the average latency for this account's device over the last 7 days?"*

These are **time-window** questions — the shape time-series binding handles well.

### Live real-time demo

```powershell
./scripts/stream_device_metrics.ps1 -AccountId ACCT000001 -IntervalSec 5 -Count 30
```
Streams fresh readings with `now()` timestamps. Then ask the agent *"what's the utilization for
account ACCT000001 in the last 5 minutes?"* to see live data arrive.

## Table schemas

All column types are chosen to be **Fabric IQ ontology-binding compatible**:
`string` (ids/categoricals), `datetime` (timestamps), `real` (continuous → ontology **Double**),
`long` (counts), `bool` (flags). **No `decimal`** (ontology returns null for Decimal), no
`dynamic`/`timespan`/`guid`.

### `DeviceMetrics`  (real-time telemetry — time-series feed)
| Column | KQL type | Notes |
|---|---|---|
| `device_id` | string | → Device (the time-series key) |
| `account_id` | string | → Account (denormalized for filtering) |
| `reading_time` | datetime | the time-series timestamp |
| `is_online` | bool | up/down state |
| `utilization_pct` | real | link utilization % |
| `downstream_mbps` | real | |
| `upstream_mbps` | real | |
| `latency_ms` | real | |

Backed by the gold dimension **`dim_customer_device`** (`device_id`, `account_id`, `customer_id`,
`model`, `device_type` modem/router, `serial_number`, `install_date`, `status`, `firmware_version`).

### `OutageEvents`
| Column | KQL type | Notes |
|---|---|---|
| `event_id` | string | key (`OEV############`) |
| `customer_id` | string | → Customer |
| `account_id` | string | → Account (the outage affects the account; one account per customer) |
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

## 1. Generate the data (local, reads the committed customers/devices)

```powershell
# The Device dimension (dim_customer_device) is produced by the main generator:
python ./data-generation/generate.py --customers 1000          # writes data/csv + data/parquet
# Then the KQL feeds (reads dim_customer.csv, dim_customer_device.csv, ...):
python ./data-generation/generate_realtime.py                  # optional: --seed 7 --as-of 2026-06-30
```

Output: `data/kql/device_metrics.csv`, `outage_events.csv`, `web_sessions.csv`, `manifest.json`
(committed). Default volumes ≈ **27,090 telemetry rows** (903 active devices × 30 days),
**380 outage rows**, **1,870 session rows**. Volume knobs live in `generate_realtime.py`
(`CONFIG`) — e.g. `metrics_readings_per_day` for a finer time series.

> The **`Device` entity** binds to the gold Lakehouse table `dim_customer_device`, which flows
> through the medallion notebooks (it's in `build_notebooks.py` `TABLES`). Re-run the Lakehouse
> load (`10_provision_fabric.ps1` + `20_load_data.ps1`, or re-run notebooks 02–03 in Fabric) so
> `gold.dim_customer_device` exists before you bind the Device entity.

## 2. Provision the Eventhouse + load the data

```powershell
./scripts/30_provision_eventhouse.ps1        # -SkipIngest to only (re)create tables
```

This creates (or reuses) the `telco_realtime` Eventhouse + KQL database, creates the three tables
(`DeviceMetrics`, `OutageEvents`, `WebSessions`), and ingests the CSVs via chunked `.ingest
inline`. It writes `KQL_DATABASE_NAME` and `KQL_QUERY_URI` to `.env`. Re-running drops + recreates
+ re-ingests (idempotent, handles schema changes, no duplicates).

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

Suggested relationships (the **mapping table** is the KQL table itself — it holds both keys).
`OutageEvents` carries **both** `account_id` and `customer_id`, so relate outages to **Account**
(recommended — an outage affects the account) and/or Customer:

| Relationship | From → To | Mapping table | from_key → to_key |
|---|---|---|---|
| `account_has_outage_event` | Account → OutageEvent | `OutageEvents` | account_id → event_id |
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
entity key `customer_id → customer_id` (or `account_id → account_id` to bind on **Account**),
**timestamp column** `event_time` (or `session_start`), and the remaining columns become
**time-varying properties** of that entity. Best for **signals over time** attached to the
customer/account. In this model there is **no `OutageEvent` node** — you don't traverse to a
child; the data is properties *of* the entity.

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
