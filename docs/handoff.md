# Developer Handoff

This document orients a developer who has just cloned the repo.

## Mental model

- **Fabric is the data backend.** Everything the agents answer comes from the Fabric Lakehouse (via the Data Agent) or the SQL endpoint (for the deterministic `customer_360` fetch). If the data backend isn't working, nothing else will.
- **Foundry is the brain.** The orchestrator routes to journey agents; those agents call the Fabric Data Agent and Foundry IQ.
- **Everything is scripted.** Azure = Bicep. Fabric = REST/`fab` CLI + notebooks. Data = Python.

## Where things live

| Path | What |
|---|---|
| `data-generation/` | Python synthetic data generator. Start here to change the dataset. |
| `data/` | Committed sample data (CSV + Parquet). Regenerate with `generate.py`. |
| `fabric/notebooks/` | Lakehouse setup + medallion load + ML scores. Runnable in Fabric directly. |
| `fabric/semantic-model/`, `fabric/ontology/` | Fabric item definitions. |
| `fabric/data-agent/` | Data Agent config + `create_data_agent.py`. |
| `scripts/` | PowerShell automation (SPN, provisioning, loading). |
| `infra/` | Bicep for Azure resources. |
| `foundry/` | Agent definitions + deployment. |
| `app/`, `teams/` | UI surfaces. |

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
| Reconfigure the Data Agent | Edit `fabric/data-agent/`, re-run `scripts/30_create_data_agent.ps1` |
| Change an agent's behavior | Edit `foundry/agents/*`, re-run `foundry/deploy_agents.ps1` |

## Gotchas

- **Fabric capacity must be F2+** for the Data Agent. The existing capacity is assumed to satisfy this.
- **Same Entra tenant** is required for Foundry ↔ Fabric Data Agent (OBO auth).
- **SPN workspace-admin grant** can be blocked by tenant policy; the setup guide has a manual fallback.
- The **SQL analytics endpoint** name/connection string is discovered after the Lakehouse is created; scripts read it back from the Fabric API.

## Status / roadmap

Track progress against the phases in the top-level plan. Phase 1 (data backend) is the gating deliverable; Phases 2–5 build on it.
