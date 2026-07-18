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
```

> By default `00_prereqs.ps1` installs only the lightweight data-generation deps (enough to
> generate data and run the web app). The Fabric Data Agent / semantic-model SDKs are heavy and
> are installed on demand by their own scripts, or you can add `-IncludeFabricSdk`. See
> [Troubleshooting](#troubleshooting) if you hit a Windows path-length error.

## 1. Data backend (Fabric) — PRIORITY

### 1a. Create the service principal
```powershell
az login
./scripts/setup_spn.ps1
```
This creates an SPN, grants it **Admin** on the Fabric workspace, and writes `SPN_APP_ID` / `SPN_CLIENT_SECRET` / `SPN_TENANT_ID` to `.env`.

> The workspace-admin grant uses the Fabric REST API (`POST /workspaces/{id}/roleAssignments`). If it fails due to tenant policy, add the SPN manually as a workspace Admin in the Fabric UI.

### 1b. Generate synthetic data
```powershell
python ./data-generation/generate.py --customers 1000
# Output: data/csv/*.csv and data/parquet/*.parquet
```

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
Deploy the definitions in `fabric/semantic-model/` and `fabric/ontology/` (scripted in `10_provision_fabric.ps1`, or import via the Fabric UI).

### 1f. Create & publish the Fabric Data Agent
```powershell
./scripts/30_create_data_agent.ps1
```
Uses `fabric-data-agent-sdk` to create the agent, attach the Lakehouse + semantic model, add per-journey instructions and example queries, and **publish**. Captures `DATA_AGENT_ARTIFACT_ID` + MCP endpoint to `.env`.

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

### Windows path-length error installing the Fabric Data Agent SDK

Symptom (during `00_prereqs.ps1 -IncludeFabricSdk` or `30_create_data_agent.ps1`):

```
ERROR: Could not install packages due to an OSError: [Errno 2] No such file or directory:
 '...\.venv\share\jupyter\labextensions\@jupyter-widgets\...<very long filename>.js'
```

Cause: `fabric-data-agent-sdk` pulls in `semantic-link-labs` -> `jupyterlab`/`ipywidgets`, whose
extension asset files exceed the Windows 260-character path limit (made worse by a long repo path).

Fixes (pick one):

1. **Enable long paths (recommended, one-time).** In an elevated PowerShell:
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
       -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
   ```
   Restart your shell, then re-run the script. (`git config --system core.longpaths true` also helps git.)

2. **Run the SDK steps inside a Fabric notebook.** The Data Agent and semantic-model SDKs are
   preinstalled in Fabric. Upload `fabric/data-agent/create_data_agent.py` /
   `fabric/semantic-model/create_semantic_model.py` into a notebook and run them there — no local
   install needed. The rest of the pipeline (data generation, Lakehouse provisioning, notebooks,
   web app) does not need these SDKs.

3. **Use a shorter repo path.** Cloning to e.g. `C:\src\telco` leaves more headroom under the
   260-char limit.

The lightweight `00_prereqs.ps1` default (data-generation deps only) does **not** hit this issue,
so you can generate data and run the web app without any of the above.
