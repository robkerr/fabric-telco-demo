# Agent Desktop Web App ("Care Console")

A FastAPI **line-of-business customer-care console** that demonstrates the live-agent context
pattern: pick a customer, the app hydrates a **Customer 360** view (identity, churn-risk gauge,
KPIs, invoices, work orders, usage charts), and an **Agent Assist** chat panel auto-routes each
message to the right **Foundry journey agent** (billing / cross-sell / service-retention) using
lightweight keyword + profile signals.

> **How it runs in this demo: fully local on the dev workstation against the committed CSV
> sample data.** No Azure/Fabric is required to run and demo the UI. Chat answers use the live
> Foundry agents *if* `FOUNDRY_PROJECT_ENDPOINT` + `foundry/agents.generated.json` are present;
> otherwise the chat falls back to a local 360 summary, so the app still works offline.

## Requirements

- Python venv with `app/requirements.txt` installed (the repo `.venv` created by
  `scripts/00_prereqs.ps1` works). Key deps: `fastapi`, `uvicorn`, `pandas` (CSV mode).
- For live **chat** (optional): `az login` as a user with access to the Foundry project + Fabric
  data agent, and `.env` pointing at the project (see repo root README / `foundry/README.md`).
- For live **360 data** (optional, not used in this demo): ODBC Driver 18 + `FABRIC_SQL_ENDPOINT`.

## Run locally (the supported path)

```powershell
cd app
../.venv/Scripts/pip install -r requirements.txt
../.venv/Scripts/python -m uvicorn main:app --reload --port 8000
# open http://localhost:8000  — search e.g. "Natasha Ryan" or "CUST000001"
```

The header badge shows `data: local` (CSV) or `data: live` (Fabric SQL), and `tracing: on/off`.

## Data source modes (automatic)

| Mode | When | 360 data source |
|---|---|---|
| **local** (default here) | otherwise | committed sample data in `../data/csv` |
| **live** | `FABRIC_SQL_ENDPOINT` + `FABRIC_LAKEHOUSE_NAME` set and `pyodbc` available | `gold.*` tables on the Fabric SQL endpoint |

Data access is abstracted behind a `DataProvider` interface in `data_access.py`
(`LocalCsvProvider` / `FabricSqlProvider`), with `COLS` as the single source of truth for the
fields each collection returns. Both providers return identical shapes, so pivoting the whole
app to Fabric is just setting the two env vars — no UI or route changes. The `FabricSqlProvider`
already implements the `gold.*` queries (`customer_360`, `fact_invoice`, `fact_work_order`,
`fact_usage_data`, `fact_usage_voice`, `ml_churn_score`, `dim_product`).

## How the chat works

1. `/api/route` picks a journey agent from keywords + the loaded 360 profile (fast, no LLM).
2. `/api/chat` runs the message against that Foundry agent (GPT-4.1), which calls the **Fabric
   Data Agent** tool to ground the answer in Lakehouse data, then composes the reply.
3. The reply is tagged with the agent that answered and carries a **`debug`** object: routing
   scores + matched keywords, per-phase timing, token usage, response id, and a trace id.

The **🐞 Debug** drawer (and the "inspect ›" link on each reply) visualizes all of that. When
`APPLICATIONINSIGHTS_CONNECTION_STRING` is set, app spans are exported to App Insights and the
drawer links to Transaction Search for the full agent-internal trace.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Care Console UI |
| GET | `/api/health` | Reports data mode (live/local) + tracing status |
| GET | `/api/search?q=` | Customer lookup (header search) |
| GET | `/api/profile/{id}` | Compact Customer 360 (used as agent context) |
| GET | `/api/account/{id}` | Full LOB detail: profile + invoices, work orders, usage series, churn |
| POST | `/api/route` | Fast routing preview (which journey agent, and why) |
| POST | `/api/chat` | Auto-route a message to the best journey agent (returns a `debug` object) |

## Deploy to Azure (optional, not required for the demo)

```powershell
./app/deploy_app.ps1     # zips + deploys to $APP_SERVICE_NAME, sets startup + settings
```

To use the live Fabric 360 path from App Service, grant the web app's managed identity access to
the Fabric workspace/SQL endpoint and set `FABRIC_SQL_ENDPOINT` in the app settings.

## Notes

- The live 360 path authenticates to the SQL endpoint with `DefaultAzureCredential` and an
  ODBC access token (ODBC Driver 18 required).
- `main.py` loads the repo `.env` for local runs; App Service injects settings directly.
