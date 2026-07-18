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

### 1e. Semantic model + ontology
Import the semantic model over the gold tables in the Fabric portal (Lakehouse -> New semantic
model), or run `fabric/semantic-model/create_semantic_model.py` **inside a Fabric notebook** (like
the Data Agent, it uses the Fabric runtime / .NET and is not run from the workstation). Apply the
measures/relationships from [`fabric/semantic-model/model_spec.yaml`](../fabric/semantic-model/model_spec.yaml).
The ontology glossary lives in [`fabric/ontology/ontology.yaml`](../fabric/ontology/ontology.yaml).

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

## 2. Azure infrastructure (Bicep)

```powershell
./infra/deploy.ps1   # deploys Foundry/AI project, AI Search, Storage, App Service, Key Vault
```
Outputs endpoints to `.env`.

## 3. Foundry agents

```powershell
./foundry/deploy_agents.ps1
```
Creates the orchestrator + 3 journey agents and adds the **Fabric Data Agent as a knowledge source** (`FABRIC_WORKSPACE_ID` + `DATA_AGENT_ARTIFACT_ID`). Wires Foundry IQ (AI Search index + semantic model) and Web IQ.

## 4. UI surfaces

- **Web App:** deploy `app/` to the App Service from step 2; configure the SQL endpoint + orchestrator endpoint.
- **Teams / M365:** side-load the manifest in `teams/`, or publish the Data Agent to M365.

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

## Reset / regenerate

- Re-run `generate.py` to rebuild data (idempotent; seeded).
- Re-run any provisioning script — all are idempotent and will update-in-place.
- Delete the Lakehouse in the workspace to start data fresh, then re-run 1c.

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
semantic model via the portal or a notebook (step 1e/1f). Everything else - data generation,
Lakehouse provisioning, the medallion notebooks, and the web app - runs locally with only
lightweight, cross-platform Python packages, so no .NET or long-path setup is required.
