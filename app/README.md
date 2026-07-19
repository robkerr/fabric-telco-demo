# Agent Desktop Web App

A FastAPI app that demonstrates the **live-agent context pattern**: when the agent opens a
customer, the app hydrates a **Customer 360** profile from the Fabric SQL analytics endpoint,
and the chat panel **auto-routes** each message to the right **Foundry journey agent**
(billing / cross-sell / service-retention) using lightweight keyword + profile signals.

## Two modes (automatic)

| Mode | When | Data source |
|---|---|---|
| **live** | `FABRIC_SQL_ENDPOINT` + `FABRIC_LAKEHOUSE_NAME` set and `pyodbc` available | `gold.*` tables on the Fabric SQL endpoint |
| **local** | otherwise | committed sample data in `../data/csv` |

Data access is abstracted behind a `DataProvider` interface in `data_access.py`
(`LocalCsvProvider` / `FabricSqlProvider`), with `COLS` as the single source of truth for
the fields each collection returns. The two providers return identical shapes, so pivoting
the whole app to Fabric is just setting the two env vars — no UI or route changes. The
`FabricSqlProvider` already implements the `gold.*` queries (`customer_360`, `fact_invoice`,
`fact_work_order`, `fact_usage_data`, `fact_usage_voice`, `ml_churn_score`).

Chat likewise routes to a Foundry journey agent when `FOUNDRY_PROJECT_ENDPOINT` +
`foundry/agents.generated.json` are present, else a local summary reply. This means the app
is fully demoable **without any cloud** — great for a first run. The reply is tagged with the
journey agent that answered.

## Run locally

```powershell
cd app
../.venv/Scripts/pip install -r requirements.txt
../.venv/Scripts/python -m uvicorn main:app --reload --port 8000
# open http://localhost:8000
```

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

## Deploy to Azure

```powershell
./app/deploy_app.ps1     # zips + deploys to $APP_SERVICE_NAME, sets startup + settings
```

The App Service uses the managed identity granted **Key Vault Secrets User** in Phase 2. To
use the live Fabric path from App Service, grant the web app's identity access to the Fabric
workspace/SQL endpoint (or store a connection secret in Key Vault) and set the app settings.

## Notes

- The live path authenticates to the SQL endpoint with `DefaultAzureCredential` and an
  ODBC access token (ODBC Driver 18 required).
- `main.py` loads the repo `.env` for local runs; App Service injects settings directly.
