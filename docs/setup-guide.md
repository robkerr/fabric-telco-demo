# Setup Guide (reproduce from scratch)

This runbook stands up the entire solution from a clean clone. **Phase 1 (data backend) is the priority** — you can stop after Phase 1 and already have a queryable Fabric Lakehouse and a published Data Agent.

There are two ways to stand up Fabric:
- **Path A — Scripted (recommended):** Windows PowerShell + Fabric REST API / `fab` CLI.
- **Path B — Manual notebooks:** upload the notebooks in `fabric/notebooks/` to your workspace and run them.

## 0. Prerequisites

- An **existing Fabric capacity + workspace** (F2 or higher). Copy its **workspace ID** (from the workspace URL or Fabric settings).
- Azure subscription + rights to create a service principal and resources.
- PowerShell 7+, [Azure CLI](https://learn.microsoft.com/cli/azure/), Python 3.10+.

```powershell
Copy-Item .env.example .env
# Edit .env: FABRIC_WORKSPACE_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, AZURE_LOCATION, AZURE_RESOURCE_GROUP
./scripts/00_prereqs.ps1        # installs fab CLI, python venv + lightweight data-gen deps, checks az
.\.venv\Scripts\Activate.ps1    # activate the venv (00_prereqs can't do it for your shell)
```

> After `00_prereqs.ps1`, **activate the venv** (`.\.venv\Scripts\Activate.ps1`) before running any
> `python` command - the script installs deps into `.venv` but can't activate it in your shell.
> Alternatively call the venv's python directly: `.\.venv\Scripts\python.exe ...`.

> `00_prereqs.ps1` installs only lightweight, cross-platform Python deps (enough to generate
> data and run the web app). The Fabric Data Agent and semantic model are created by running
> **Fabric notebooks** (they depend on the Fabric runtime / .NET), not from your workstation, so
> no heavy SDKs are installed locally.

## 1. Data backend (Fabric) — PRIORITY

### 1a. Generate synthetic data (local, no cloud needed)
```powershell
python ./data-generation/generate.py --customers 1000
# Output: data/csv/*.csv and data/parquet/*.parquet
```
This is fully local and independent of Azure/Fabric. At this point you can already run the
web app in local mode (see [Try it instantly](#try-it-instantly-no-cloud)).

### 1b. Create the service principal
```powershell
az login
./scripts/setup_spn.ps1
```
This creates an SPN, grants it **Admin** on the Fabric workspace, and writes `SPN_APP_ID` / `SPN_CLIENT_SECRET` / `SPN_TENANT_ID` to `.env`.

> The workspace-admin grant uses the Fabric REST API (`POST /workspaces/{id}/roleAssignments`) and
> retries while the new SP propagates. If it still fails, add the SPN manually: **Workspace ->
> Manage access -> Add people or groups**, and **search by the SP display name**
> (`sp-telco-fabric-demo`) - the picker searches by name, not by app/object ID - then assign
> **Admin**. Also confirm the tenant setting **"Service principals can use Fabric APIs"** is enabled.

### 1c. Provision the Lakehouse + upload notebooks

**Path A (scripted):**
```powershell
./scripts/10_provision_fabric.ps1   # creates the Lakehouse, uploads notebooks + parquet
./scripts/20_load_data.ps1          # runs 02_load_bronze -> 03_build_silver_gold -> 04_ml_scores
```

**Path B (manual):**
1. In the workspace, create a Lakehouse named `TelcoLakehouse`.
2. Upload the `data/parquet/*.parquet` files to the Lakehouse **Files** area (e.g. `Files/landing/`).
3. Import the notebooks from `fabric/notebooks/` and run them in order: `01` → `02` → `03` → `04`.

### 1d. Verify the SQL endpoint (Customer 360)
```powershell
./scripts/verify_customer360.ps1    # runs a sample fetch against the SQL analytics endpoint
```
`customer_360` is built by notebook `04_ml_scores` (it depends on the ML score tables); the
notebook's final cell also prints a validation sample.

### 1e. Semantic model + ontology (manual, Fabric portal)

Both were built **by hand in the Fabric portal** in this demo:

- **Semantic model** — in the Lakehouse, use **New semantic model** (the bootstrap button),
  name it `TelcoCustomerService`, select the **gold** tables, then add the relationships +
  DAX measures from [`fabric/semantic-model/model_spec.yaml`](../fabric/semantic-model/model_spec.yaml)
  (web editor or Tabular Editor). See [`fabric/semantic-model/README.md`](../fabric/semantic-model/README.md).
- **Ontology (Fabric IQ)** — open the semantic model and **Generate Ontology**, or build one
  from OneLake, then define the 11 entity types + 10 relationships. The critical gotcha (a
  relationship's *mapping table* must contain both keys) and the full entity/relationship list
  are in [`fabric/ontology/README.md`](../fabric/ontology/README.md); `ontology.yaml` mirrors the
  built item. You can pull the live definition back with `./scripts/export_ontology.ps1`.

### 1f. Create & publish the Fabric Data Agent (run in Fabric)

The Data Agent is created by running a **Fabric notebook** - it uses the Fabric runtime for
authentication and .NET, so it is not created from your local workstation.

1. `10_provision_fabric.ps1` already uploaded the **`05_create_data_agent`** notebook to your
   workspace. Open it in Fabric.
2. Attach **your Lakehouse** (whatever you named it, e.g. `lh_telco`) as the default Lakehouse
   (Explorer panel, "Add" / pin). The notebook auto-detects the attached Lakehouse.
3. **Run all.** The notebook installs `fabric-data-agent-sdk`, creates the agent, applies the AI
   instructions, and attaches the Lakehouse as a data source.
4. **Finish in the Data Agent UI:** open the **TelcoCustomerServiceAgent** agent, **select the
   `gold`-schema tables** (check the `gold` schema to include all of them), optionally add example
   queries from `config.yaml`, and click **Publish**. (Programmatic table selection isn't reliable
   across SDK versions, so this step is done in the UI.)
5. Copy the printed **`DATA_AGENT_ARTIFACT_ID`** and **`DATA_AGENT_MCP_ENDPOINT`** into your
   local `.env` (the Foundry agents in Phase 3 bind to these; the MCP endpoint works after publish).

The notebook's config is generated from [`fabric/data-agent/config.yaml`](../fabric/data-agent/config.yaml)
(embedded when the notebooks are built), which stays the single source of truth for the agent's
name, instructions, and the example queries you can paste in the UI.

**Phase 1 done when:** committed data is loaded, `customer_360` returns rows over the SQL endpoint, and the Data Agent answers journey questions.

## 2. Azure / Foundry setup

You need an **Azure AI Foundry project** with a **gpt-4.1** deployment and three project
connections (Fabric Data Agent, Azure AI Search, Bing). You can either **reuse an existing
Foundry resource group/project** (what this demo did) or deploy fresh with the Bicep in
`infra/`:

```powershell
./infra/deploy.ps1   # optional — provisions a Foundry account+project, AI Search, Key Vault, Log Analytics
```

Then, whichever route:
- Deploy **gpt-4.1** on the project's account and set `.env` `FOUNDRY_MODEL=gpt-4.1`
  (⚠️ the Agent Service tools are **not supported on gpt-5** in westus3).
- Build the product-KB search index: `./.venv/Scripts/python foundry/setup_knowledge.py`.
- Create the three **project connections** in the Foundry portal and record their names in `.env`
  (`FABRIC_CONNECTION_NAME`, `AI_SEARCH_CONNECTION_NAME`, `BING_CONNECTION_NAME`).
- (Optional) `./foundry/setup_tracing.ps1` to provision + connect Application Insights.

Full required-resources checklist: [`foundry/README.md`](../foundry/README.md).

## 3. Foundry agents

```powershell
az login                      # as a USER (Fabric data-agent tool uses on-behalf-of, not the SPN)
./foundry/deploy_agents.ps1
```
Creates the **three independent journey agents** (`telco-BillingFirstBillAgent`,
`telco-CrossSellAgent`, `telco-ServiceRetentionAgent`) on gpt-4.1, each with the Fabric Data
Agent tool (+ AI Search / Bing where relevant), and writes `foundry/agents.generated.json`.
There is no orchestrator agent — the web app routes to these.

## 4. Web app (Care Console)

The web app runs **locally on the committed CSV data** — see [Try it instantly](#try-it-instantly-no-cloud)
below and [`app/README.md`](../app/README.md). It picks up the deployed agents automatically via
`foundry/agents.generated.json` + `FOUNDRY_PROJECT_ENDPOINT`. Deploying to Azure App Service
(`app/deploy_app.ps1`) and the live Fabric SQL 360 path are optional. Teams / M365 Copilot is
scaffolded in `teams/` for the future.

## 5. Demo

Follow the scripted walkthroughs in [`demo-scenarios.md`](demo-scenarios.md) (one per journey,
with real customer IDs).

### Try it instantly (no cloud)

The agent-desktop web app runs in **local mode** off the committed sample data — no Fabric or
Foundry required — so you can demo the Customer 360 + chat flow right after generating data:

```powershell
python ./data-generation/generate.py --customers 1000   # if not already done
./.venv/Scripts/pip install -r app/requirements.txt
cd app; ../.venv/Scripts/python -m uvicorn main:app --port 8000
# open http://localhost:8000  (search e.g. CUST000003, CUST000730, CUST000783)
```

## Reset to a clean slate

The provisioning scripts are idempotent and **reuse** existing items when they find them. To
force a truly clean, from-scratch run, reset these first (Windows PowerShell, repo root):

**1. Local Python environment**
```powershell
deactivate                              # only if your prompt shows (.venv); ignore any error
Remove-Item -Recurse -Force .venv       # 00_prereqs.ps1 recreates it
```

**2. Local `.env`** (clear stale IDs so scripts don't reuse old resources)
```powershell
Copy-Item .env.example .env -Force
# Re-enter your inputs (FABRIC_WORKSPACE_ID, AZURE_*, FABRIC_LAKEHOUSE_NAME). Leave SPN_*,
# FABRIC_LAKEHOUSE_ID, DATA_AGENT_*, FOUNDRY_*, AI_SEARCH_*, APP_*/KEY_VAULT_* blank — the
# scripts repopulate them. A leftover id is exactly what makes a script "skip" creating something.
```

**3. Fabric workspace** — delete the whole **workspace** (cleanest), or delete individually: the
**Lakehouse**, the `01`-`05` **notebooks**, the **Data Agent(s)**, the **semantic model**, and the
**ontology**. If you make a new workspace, put its id in `FABRIC_WORKSPACE_ID`.

**4. Entra service principal**
```powershell
$appId = (Get-Content .env | Where-Object { $_ -match '^SPN_APP_ID=' }) -replace '^SPN_APP_ID=',''
if ($appId) { az ad app delete --id $appId }   # or delete 'sp-telco-fabric-demo' in the Entra portal
```
> Delete before you blank `SPN_APP_ID` in step 2. Soft-deleted apps sit in **Entra ID -> App
> registrations -> Deleted applications** for 30 days; purge there to remove immediately.

**5. Foundry agents / Azure infra**
```powershell
# remove the deployed agents by re-running deploy (it retires old names), or delete them in the
# Foundry portal. If you deployed fresh infra in Phase 2:
az group delete --name <AZURE_RESOURCE_GROUP> --yes --no-wait
```

**6. (Optional) regenerate data** — committed already; only needed if you changed the generator:
`python ./data-generation/generate.py --customers 1000`.

Then rerun from Phase 1. Quick regenerate without a full reset: re-run `generate.py` (seeded,
idempotent) and any provisioning script (all update-in-place).

## Troubleshooting

### Why are the Data Agent and semantic model created in Fabric notebooks?

They depend on the Fabric runtime and .NET interop (`sempy` / `pythonnet`), which is not designed
to run from a local workstation - and does not work at all on **ARM64 Windows (Snapdragon /
Copilot+ PCs)**, where you would see:

```
RuntimeError: Could not find a suitable hostfxr library in C:\Program Files\dotnet
cannot load library '...\hostfxr.dll': error 0xc1
```

That's why this solution creates the Data Agent via the **`05_create_data_agent`** notebook and the
semantic model + ontology in the portal (step 1e/1f). Everything else - data generation,
Lakehouse provisioning, the medallion notebooks, and the web app - runs locally with only
lightweight, cross-platform Python packages, so no .NET or long-path setup is required.
