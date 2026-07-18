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
| Data | Fabric **Data Agent** (MCP endpoint) | `fabric-data-agent-sdk` (Python) |
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

# 2. Install tooling (az, fab CLI, python venv + deps)
./scripts/00_prereqs.ps1

# 3. Create a service principal and grant it admin on the workspace
./scripts/setup_spn.ps1

# 4. Generate synthetic data (default: 1000 customers) into ./data
python ./data-generation/generate.py --customers 1000

# 5. Provision the Lakehouse and upload notebooks into the workspace
./scripts/10_provision_fabric.ps1

# 6. Load the data (runs the load notebooks)
./scripts/20_load_data.ps1

# 7. Create & publish the Fabric Data Agent
./scripts/30_create_data_agent.ps1
```

Phases 2–5 (Azure infra, Foundry agents, Web App, Teams) are documented in [`docs/setup-guide.md`](docs/setup-guide.md).

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
