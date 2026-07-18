# Agent Desktop Web App

A FastAPI app that demonstrates the **live-agent context pattern**: when the agent opens a
customer, the app hydrates a **Customer 360** profile from the Fabric SQL analytics endpoint,
and the chat panel routes messages to the **Foundry orchestrator**.

## Two modes (automatic)

| Mode | When | Data source |
|---|---|---|
| **live** | `FABRIC_SQL_ENDPOINT` + `FABRIC_LAKEHOUSE_NAME` set and `pyodbc` available | `customer_360` on the Fabric SQL endpoint |
| **local** | otherwise | committed sample data in `../data/csv` |

Chat likewise uses the Foundry orchestrator when `FOUNDRY_PROJECT_ENDPOINT` +
`foundry/agents.generated.json` are present, else a local summary reply. This means the app
is fully demoable **without any cloud** — great for a first run.

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
| GET | `/` | Agent desktop UI |
| GET | `/api/health` | Reports data mode (live/local) |
| GET | `/api/search?q=` | Customer lookup |
| GET | `/api/profile/{id}` | Customer 360 fetch-on-contact |
| POST | `/api/chat` | Route a message to the orchestrator |

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
