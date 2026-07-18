# Telco Customer Service AI — Fabric + Foundry Demo

A reference solution that builds a **customer-service AI experience for a Telecommunications company** on:

- **Microsoft Fabric** — the data platform (Lakehouse, SQL analytics endpoint, semantic model, ontology, Data Agent)
- **Microsoft Foundry** — the agent platform (v2 Agent Service, Foundry IQ, Web IQ)
- **Azure Web App + Teams / M365 Copilot** — the UI surfaces

Because we start with **no data**, the solution first generates a **synthetic telco dataset**, seeds a **Fabric Lakehouse**, and exposes it to Foundry agents. Everything is reproducible from this repo using **Windows PowerShell** and/or by **uploading and running the Fabric notebooks**.

> **Start here:** the data backend (Phase 1) is the foundation. See [`docs/setup-guide.md`](docs/setup-guide.md) for the full runbook.

## What gets built

| Layer | Item | How it's created |
|---|---|---|
| Data | Lakehouse (Bronze/Silver/Gold Delta) + `customer_360` | Notebooks + PowerShell (Fabric REST / `fab` CLI) |
| Data | Semantic model + ontology | Fabric item definitions |
| Data | Fabric **Data Agent** (MCP endpoint) | `05_create_data_agent` notebook (run in Fabric) |
| Azure | Foundry/AI project, AI Search, Storage, App Service, Key Vault | Bicep |
| Agents | Orchestrator + 3 journey agents | Foundry Agent Service |
| UI | Agent desktop web app + Teams/M365 Copilot | App Service + Teams manifest |

## Prerequisites

- **Existing Fabric capacity + workspace** (F2 or higher). You supply the workspace ID.
- Azure subscription with rights to create resources and a service principal.
- Windows PowerShell 5.1+ / PowerShell 7+, [Azure CLI](https://learn.microsoft.com/cli/azure/), Python 3.10+.
- The [Fabric CLI](https://learn.microsoft.com/fabric/fundamentals/fabric-cli) (`fab`) — installed by `scripts/00_prereqs.ps1`.

## Quickstart

```powershell
# 1. Copy and fill in environment values
Copy-Item .env.example .env
#    -> set FABRIC_WORKSPACE_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, etc.

# 2. Install tooling (az, fab CLI, python venv + lightweight data-gen deps)
./scripts/00_prereqs.ps1

# 3. Generate synthetic data (default: 1000 customers) into ./data
#    This is fully local - no Azure/Fabric needed. You can demo the web app now
#    ("Try it instantly" below).
python ./data-generation/generate.py --customers 1000

# --- The steps below provision Fabric and require az login + your workspace ---

# 4. Create a service principal and grant it admin on the workspace
az login
./scripts/setup_spn.ps1

# 5. Provision the Lakehouse and upload notebooks into the workspace
./scripts/10_provision_fabric.ps1

# 6. Load the data (runs the load notebooks)
./scripts/20_load_data.ps1

# 7. Create the Fabric Data Agent -- run IN FABRIC (not locally):
#    open the "05_create_data_agent" notebook, attach your Lakehouse, Run all.
#    Then in the Data Agent UI: select the gold-schema tables + Publish, and copy
#    DATA_AGENT_ARTIFACT_ID + DATA_AGENT_MCP_ENDPOINT into .env.
```

Phases 2–5 (Azure infra, Foundry agents, Web App, Teams) are documented in [`docs/setup-guide.md`](docs/setup-guide.md).

## Try it instantly (no cloud)

The agent-desktop web app runs in **local mode** off the committed sample data — no Fabric or
Foundry needed:

```powershell
python ./data-generation/generate.py --customers 1000
./.venv/Scripts/pip install -r app/requirements.txt
cd app; ../.venv/Scripts/python -m uvicorn main:app --port 8000
# open http://localhost:8000  (search CUST000003, CUST000730, or CUST000783)
```

See [`docs/demo-scenarios.md`](docs/demo-scenarios.md) for the three journey walkthroughs.

## Solution phases

| Phase | What | Key scripts / assets |
|---|---|---|
| **1. Data backend (priority)** | Synthetic data → Lakehouse → `customer_360` → semantic model + ontology → **Fabric Data Agent** | `data-generation/`, `fabric/`, `scripts/10`–`20`, `05_create_data_agent` notebook |
| **2. Azure infra** | Foundry, AI Search, Storage, Key Vault, App Service | `infra/` (Bicep) |
| **3. Foundry agents** | Orchestrator + 3 journey agents, knowledge sources | `foundry/` |
| **4. UI** | Agent-desktop web app + Teams/M365 | `app/`, `teams/` |
| **5. Demo** | Journey walkthroughs | `docs/demo-scenarios.md` |

## Repository layout

```
docs/            architecture, data model, setup runbook, handoff notes
infra/           Azure resources (Bicep) + deploy.ps1
scripts/         PowerShell + Python automation (SPN, provisioning, loading)
data-generation/ synthetic telco data generator (Python)
data/            generated sample data (CSV + Parquet) committed to the repo
fabric/          Fabric items-as-code: notebooks, semantic model, ontology, data agent
foundry/         Foundry agent definitions + orchestration
app/             Azure Web App (agent desktop / 360 profile)
teams/           Teams / M365 Copilot manifest & wiring
```

## Reproducibility

- Every script is idempotent and re-runnable.
- No secrets in the repo — they live in `.env` (git-ignored) and/or Key Vault. `.env.example` documents every value.
- Two ways to stand up Fabric: PowerShell + REST/`fab` CLI, **or** manual notebook upload + run (both in the setup guide).
- Synthetic data is committed so the Lakehouse can be seeded without regenerating; `generate.py` lets you regenerate or scale up.

See [`docs/handoff.md`](docs/handoff.md) for a new-developer orientation.

## Reset to a clean slate (start-from-scratch testing)

The provisioning scripts are idempotent and **reuse** existing items (Lakehouse, notebooks,
service principal, data agent) when they find them. To force a truly clean run so nothing is
skipped, reset these before rerunning (Windows PowerShell, from the repo root):

**1. Local Python environment**
```powershell
deactivate                              # only if your prompt shows (.venv); ignore any error
Remove-Item -Recurse -Force .venv       # 00_prereqs.ps1 recreates it
```

**2. Local `.env` (clear stale IDs so scripts don't reuse old resources)**
```powershell
Copy-Item .env.example .env -Force
# then re-enter your inputs in .env:
#   FABRIC_WORKSPACE_ID   = <your NEW workspace id>
#   AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID, AZURE_LOCATION, AZURE_RESOURCE_GROUP
#   FABRIC_LAKEHOUSE_NAME = <e.g. lh_telco>   (no spaces)
# Leave SPN_*, FABRIC_LAKEHOUSE_ID, DATA_AGENT_*, FOUNDRY_*, AI_SEARCH_*, APP_SERVICE_NAME,
# KEY_VAULT_NAME blank - the scripts repopulate them.
```
Recreating `.env` from the template is the safest step: a leftover `FABRIC_LAKEHOUSE_ID`,
`SPN_APP_ID`, or `DATA_AGENT_ARTIFACT_ID` is exactly what makes a script "skip" creating something.

**3. Fabric workspace** — delete the whole **workspace** (cleanest), or delete these items
individually: the **Lakehouse**, the `01`-`05` **notebooks**, the **Data Agent**, and any
**semantic model**. If you create a new workspace, put its id in `FABRIC_WORKSPACE_ID`.

**4. Entra service principal** — delete the app registration (this also removes its service
principal + secret):
```powershell
$appId = (Get-Content .env | Where-Object { $_ -match '^SPN_APP_ID=' }) -replace '^SPN_APP_ID=',''
if ($appId) { az ad app delete --id $appId }   # or delete 'sp-telco-fabric-demo' in the Entra portal
```
> Deleting before you blank `SPN_APP_ID` in step 2. The soft-deleted app sits in
> **Entra ID -> App registrations -> Deleted applications** for 30 days; a new app with the same
> name is fine (names aren't unique). Purge it there if you want it gone immediately.

**5. Azure infrastructure (only if you ran Phase 2 / `infra/deploy.ps1`)**
```powershell
az group delete --name <AZURE_RESOURCE_GROUP> --yes --no-wait
```

**6. (Optional) regenerate data** - the sample data is committed, so this is only needed if you
changed the generator: `python ./data-generation/generate.py --customers 1000`.

Then rerun from the [Quickstart](#quickstart): `00_prereqs.ps1` -> generate data -> `setup_spn.ps1`
-> `10_provision_fabric.ps1` -> `20_load_data.ps1` -> `verify_customer360.ps1` -> the `05` notebook.
