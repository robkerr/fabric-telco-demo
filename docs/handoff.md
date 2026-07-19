# Developer Handoff

This document orients a developer who has just cloned the repo.

## Mental model

- **Fabric is the data backend.** Everything the agents answer comes from the Fabric Lakehouse (via the Data Agent) or the SQL endpoint (for the deterministic `customer_360` fetch). If the data backend isn't working, nothing else will.
- **Foundry runs the agents.** Three independent journey agents (gpt-4.1) call the Fabric Data Agent (+ AI Search / Bing). Intent routing is done **in the web app** (keyword + profile) — there is no orchestrator agent.
- **Mostly scripted, some manual.** Data = Python. Fabric provisioning/load = PowerShell + notebooks. Foundry agents = `deploy_agents.ps1`. The **semantic model + ontology were built manually in the Fabric portal** (documented in their READMEs). Azure infra Bicep exists but this demo **reused an existing Foundry resource group/project**.

## Where things live

| Path | What |
|---|---|
| `data-generation/` | Python synthetic data generator. Start here to change the dataset. |
| `data/` | Committed sample data (CSV + Parquet). Regenerate with `generate.py`. |
| `fabric/notebooks/` | Lakehouse setup + medallion load + ML scores + `05_create_data_agent`. Run in Fabric. |
| `fabric/semantic-model/`, `fabric/ontology/` | Specs (`model_spec.yaml`, `ontology.yaml`) + READMEs for the **manually built** model + ontology. |
| `fabric/data-agent/` | Data Agent `config.yaml` (embedded into the `05_create_data_agent` notebook). |
| `scripts/` | PowerShell automation (SPN, provisioning, loading, `export_ontology.ps1`). |
| `infra/` | Bicep for Azure resources (optional — this demo reused an existing Foundry RG). |
| `foundry/` | Agent definitions + `deploy_agents.ps1` + `setup_knowledge.ps1` + `setup_tracing.ps1`. |
| `app/` | Care Console web app (runs locally on CSV). `teams/` | Teams/M365 scaffolding (future). |

## Secrets

- Local: `.env` (git-ignored). `.env.example` documents every key.
- Deployed: **Key Vault** (provisioned by `infra/`).
- The **service principal** created by `setup_spn.ps1` is the identity used by all provisioning scripts and is a **workspace Admin**. Rotate its secret with `az ad app credential reset`.

## Common tasks

| I want to... | Do this |
|---|---|
| Change the data shape | Edit `data-generation/generators/*`, re-run `generate.py` |
| Add more customers | `python data-generation/generate.py --customers 10000` |
| Re-seed the Lakehouse | Re-run `scripts/10_provision_fabric.ps1` + `scripts/20_load_data.ps1` |
| Reconfigure the Data Agent | Edit `fabric/data-agent/config.yaml`, rebuild notebooks (`python fabric/notebooks/build_notebooks.py`), re-import (`10_provision_fabric.ps1 -SkipUpload`), and re-run the `05_create_data_agent` notebook in Fabric |
| Change an agent's behavior | Edit `foundry/agents/*`, re-run `foundry/deploy_agents.ps1` |

## Gotchas

- **Foundry model must be gpt-4.1 / gpt-4o.** The Agent Service tools (Fabric / AI Search / Bing) are **not supported on gpt-5** in westus3 — the portal shows "not supported by the selected model" and agents return no tool data.
- **`deploy_agents.ps1` runs as a user, not the SPN.** The Fabric Data Agent tool uses on-behalf-of auth (`az login` as a user with access to the data agent + data sources).
- **Windows-on-Arm** can't run the Fabric Python SDKs (sempy / data-agent-sdk) locally — run those in Fabric notebooks / the portal.
- **Fabric capacity must be F2+** for the Data Agent, in the **same Entra tenant** as Foundry.
- **SPN workspace-admin grant** can be blocked by tenant policy; the setup guide has a manual fallback.

## Status / roadmap

Phases 1–4 are complete (data backend, Fabric items, reused Foundry setup, agents, Care Console).
Teams / M365 Copilot is scaffolded in `teams/` but not wired. See the status table in the
[root README](../README.md).
