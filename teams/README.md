# Teams / M365 Copilot Surface

Three complementary ways to bring the solution into Teams / Microsoft 365. Pick the one that
fits your demo.

## Option A — Publish the Fabric Data Agent to M365 Copilot (lowest effort)

The published Fabric Data Agent (Phase 1) can be surfaced directly in Microsoft 365 Copilot.
Do this from **within Fabric** (portal, or the SDK run inside a Fabric notebook) — publishing to
M365 isn't in the public API yet. Users then query telco data in natural language from Copilot.

## Option B — Teams static tab embedding the Agent Desktop

[`manifest.json`](manifest.json) defines a Teams personal app with a **static tab** that embeds
the web app from Phase 4. Steps:

1. Deploy the web app (`app/deploy_app.ps1`) and note its host name.
2. Replace `REPLACE_WITH_WEBAPP_HOST` (contentUrl, websiteUrl, validDomains) and
   `REPLACE_WITH_ENTRA_APP_ID` in `manifest.json`.
3. Add `color.png` (192×192) and `outline.png` (32×32) icons to this folder.
4. Zip `manifest.json` + the two icons and side-load it in Teams (Apps → Manage your apps →
   Upload a custom app).

## Option C — Declarative agent for M365 Copilot

[`declarativeAgent.json`](declarativeAgent.json) is a declarative-agent manifest for M365
Copilot with telco instructions and conversation starters. Package it with a Teams app
manifest (using the [Teams Toolkit](https://learn.microsoft.com/microsoftteams/platform/toolkit/teams-toolkit-fundamentals)
or Copilot Studio) and publish. To ground it in live data, add an action that calls the
Foundry orchestrator or the Fabric Data Agent MCP endpoint.

## Which to use

| Goal | Option |
|---|---|
| Fastest "chat with telco data in Copilot" | A |
| Full agent-desktop experience (360 + chat) in Teams | B |
| Native Copilot declarative agent with starters | C |

See [`../docs/architecture.md`](../docs/architecture.md) for how these surfaces connect to the
orchestrator and the Fabric data layer.
