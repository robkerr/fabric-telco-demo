# Foundry Agents (Phase 3)

Three **independent journey agents**, each grounded in the Fabric Data Agent and Foundry IQ
knowledge sources:

```
telco-BillingFirstBillAgent      (first-bill support)      -> Fabric Data Agent
telco-CrossSellAgent             (acquisition + cross-sell) -> Fabric Data Agent + AI Search + Web
telco-ServiceRetentionAgent      (degradation + retention)  -> Fabric Data Agent + Web
```

> Note: automatic orchestrator/connected-agent delegation is **not** wired. The current Foundry
> SDK (`azure-ai-projects` 2.x) has no `ConnectedAgentTool` — multi-agent orchestration needs the
> preview workflow/A2A APIs. Each agent stands alone and can be invoked directly.

## Prerequisites

- **Sign in as a user** (`az login`). The Fabric data agent tool uses identity passthrough
  (On-Behalf-Of) and does **not** support service principals. The signed-in user needs access to
  the Fabric data agent and its data sources.
- The tool **connections** below must exist in the project and their names set in `.env`.

## Deploy

```powershell
az login
./foundry/deploy_agents.ps1
```

Creates the agents in the project (`FOUNDRY_PROJECT_ENDPOINT`) from
[`agents/agents.yaml`](agents/agents.yaml) via `project.agents.create_version(...)`, and writes
their name/id/version to `agents.generated.json`.

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
knowledge source, install the Foundry Python deps, then create the Azure AI Search index and
upload the docs:

```powershell
./.venv/Scripts/python -m pip install -r foundry/requirements.txt
./.venv/Scripts/python foundry/setup_knowledge.py
```

Then create an AI Search connection in the Foundry project and set `AI_SEARCH_CONNECTION_NAME`.

## Tracing / observability

Enable end-to-end tracing of agent runs in the portal (**your project > Tracing**):

```powershell
az login
./foundry/setup_tracing.ps1
```

This idempotently provisions a **workspace-based Application Insights** resource (backed by the
Log Analytics workspace in the resource group), connects it to the Foundry project as an
`AppInsights` connection, and writes `APP_INSIGHTS_NAME` +
`APPLICATIONINSIGHTS_CONNECTION_STRING` to `.env`. A project allows only **one** AppInsights
connection, so re-running reuses the existing one. Run an agent, then refresh the Tracing tab
(traces can take 1–3 minutes to appear). The connection string is also emitted for optional
client-side (web app) OpenTelemetry export.

## How the journeys use the agents

| Journey | Agent | Data grounding |
|---|---|---|
| First-bill support | telco-BillingFirstBillAgent | invoices, invoice lines, subscriptions |
| Acquisition + cross-sell | telco-CrossSellAgent | subscriptions, `ml_crosssell_reco`, promotions, product docs |
| Degradation + retention | telco-ServiceRetentionAgent | outages, service metrics, work orders, `ml_churn_score`, offers |

See [`../docs/architecture.md`](../docs/architecture.md) for the full picture.
