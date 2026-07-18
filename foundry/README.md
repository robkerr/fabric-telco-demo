# Foundry Agents (Phase 3)

The agent platform: an **orchestrator** plus three **journey agents**, grounded in the
Fabric Data Agent and Foundry IQ knowledge sources.

```
TelcoOrchestrator
├─ BillingFirstBillAgent      (first-bill support)      -> Fabric Data Agent
├─ CrossSellAgent            (acquisition + cross-sell) -> Fabric Data Agent + AI Search + Web
└─ ServiceRetentionAgent     (degradation + retention)  -> Fabric Data Agent + Web
```

## Deploy

```powershell
az login
./foundry/deploy_agents.ps1
```

This creates the agents in the Foundry project (`FOUNDRY_PROJECT_ENDPOINT`) from
[`agents/agents.yaml`](agents/agents.yaml) and writes their IDs to `agents.generated.json`.

## Connections (set these up once, then re-run deploy)

Agent tools bind to **project connections**. Create them in the Foundry portal (or CLI)
and record their names in `.env`:

| Tool | Connection | .env key |
|---|---|---|
| Fabric Data Agent | Microsoft Fabric connection to the published data agent (`FABRIC_WORKSPACE_ID` + `DATA_AGENT_ARTIFACT_ID`) | `FABRIC_CONNECTION_NAME` |
| Azure AI Search | Connection to the AI Search service from Phase 2 | `AI_SEARCH_CONNECTION_NAME`, `AI_SEARCH_INDEX` |
| Web IQ | Bing grounding connection (optional) | `BING_CONNECTION_NAME` |

`deploy_agents.py` attaches whatever connections it can find and clearly logs any it can't,
so you can create the connection and re-run without losing progress. The Fabric data agent
must be **published** (Phase 1) and in the **same Entra tenant** as Foundry (on-behalf-of auth).

## Foundry IQ knowledge source (product literature / KB)

[`knowledge/`](knowledge) holds sample product literature. To use it as a Foundry IQ
knowledge source, create the Azure AI Search index and upload the docs:

```powershell
./.venv/Scripts/python foundry/setup_knowledge.py
```

Then create an AI Search connection in the Foundry project and set `AI_SEARCH_CONNECTION_NAME`.

## How the journeys use the agents

| Journey | Agent | Data grounding |
|---|---|---|
| First-bill support | BillingFirstBillAgent | invoices, invoice lines, subscriptions |
| Acquisition + cross-sell | CrossSellAgent | subscriptions, `ml_crosssell_reco`, promotions, product docs |
| Degradation + retention | ServiceRetentionAgent | outages, service metrics, work orders, `ml_churn_score`, offers |

See [`../docs/architecture.md`](../docs/architecture.md) for the full picture.
