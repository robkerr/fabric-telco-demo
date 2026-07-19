"""
Deploy the Telco Foundry agents from foundry/agents/agents.yaml.

Creates the journey agents and the orchestrator in the Azure AI Foundry project, wiring:
  - the Fabric Data Agent as a knowledge/tool source (via a project connection)
  - Azure AI Search (Foundry IQ knowledge source)
  - Web grounding (Web IQ)
  - connected-agent delegation from the orchestrator to the journey agents

Environment (from repo .env):
    FOUNDRY_PROJECT_ENDPOINT   Azure AI Foundry project endpoint
    FOUNDRY_MODEL              optional model override (default from agents.yaml)
    FABRIC_CONNECTION_NAME     project connection name for the Fabric data agent
    AI_SEARCH_CONNECTION_NAME  project connection name for Azure AI Search
    AI_SEARCH_INDEX            search index name (default 'telco-knowledge')
    BING_CONNECTION_NAME       optional Bing grounding connection for Web IQ
    FABRIC_WORKSPACE_ID / DATA_AGENT_ARTIFACT_ID  used to describe the Fabric source

Because the Foundry agent SDK surface evolves and some tools require connections that are
created in the portal, tool attachment is best-effort: missing pieces are logged and the
agents are still created. Agent IDs are written to foundry/agents.generated.json.

Docs: https://learn.microsoft.com/azure/ai-foundry/agents/
      https://learn.microsoft.com/azure/ai-foundry/agents/how-to/tools/fabric
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SPEC = HERE / "agents" / "agents.yaml"
OUT = HERE / "agents.generated.json"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def get_connection_id(project, name):
    if not name:
        return None
    try:
        for conn in project.connections.list():
            if getattr(conn, "name", None) == name:
                return getattr(conn, "id", None)
    except Exception as ex:  # noqa: BLE001
        print(f"  (connection lookup failed: {ex})")
    return None


def build_tools(project, tool_keys, ctx):
    """Return (tools, tool_resources_notes). Best-effort across SDK versions."""
    tools = []
    for key in tool_keys:
        if key == "fabric_data_agent":
            _add_fabric_tool(project, tools, ctx)
        elif key == "azure_ai_search":
            _add_search_tool(project, tools, ctx)
        elif key == "web":
            _add_web_tool(project, tools, ctx)
        # connected_agents handled by caller (needs created journey ids)
    return tools


def _add_fabric_tool(project, tools, ctx):
    conn_id = get_connection_id(project, os.environ.get("FABRIC_CONNECTION_NAME"))
    try:
        from azure.ai.agents.models import FabricTool
        if conn_id:
            tools.extend(FabricTool(connection_id=conn_id).definitions)
            print("  + Fabric data agent tool attached")
            return
    except Exception as ex:  # noqa: BLE001
        print(f"  (Fabric tool unavailable: {ex})")
    print("  ! Fabric tool NOT attached. Create a Foundry connection to the Fabric data "
          f"agent (workspace {ctx.get('workspace_id')}, artifact {ctx.get('artifact_id')}) "
          "and set FABRIC_CONNECTION_NAME in .env, then re-run.")


def _add_search_tool(project, tools, ctx):
    conn_id = get_connection_id(project, os.environ.get("AI_SEARCH_CONNECTION_NAME"))
    index = os.environ.get("AI_SEARCH_INDEX", "telco-knowledge")
    try:
        from azure.ai.agents.models import AzureAISearchTool
        if conn_id:
            tools.extend(AzureAISearchTool(index_connection_id=conn_id, index_name=index).definitions)
            print("  + Azure AI Search tool attached")
            return
    except Exception as ex:  # noqa: BLE001
        print(f"  (Search tool unavailable: {ex})")
    print("  ! Azure AI Search tool NOT attached. Create a Foundry connection to AI Search "
          "and set AI_SEARCH_CONNECTION_NAME + AI_SEARCH_INDEX in .env.")


def _add_web_tool(project, tools, ctx):
    conn_id = get_connection_id(project, os.environ.get("BING_CONNECTION_NAME"))
    try:
        from azure.ai.agents.models import BingGroundingTool
        if conn_id:
            tools.extend(BingGroundingTool(connection_id=conn_id).definitions)
            print("  + Web (Bing grounding) tool attached")
            return
    except Exception as ex:  # noqa: BLE001
        print(f"  (Web tool unavailable: {ex})")
    print("  ! Web IQ tool NOT attached (optional). Set BING_CONNECTION_NAME to enable.")


def main() -> int:
    load_env_file(REPO / ".env")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("ERROR: FOUNDRY_PROJECT_ENDPOINT not set (run infra/deploy.ps1 first).",
              file=sys.stderr)
        return 1

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    model = os.environ.get("FOUNDRY_MODEL", spec.get("model", "gpt-5-mini"))
    ctx = {
        "workspace_id": os.environ.get("FABRIC_WORKSPACE_ID"),
        "artifact_id": os.environ.get("DATA_AGENT_ARTIFACT_ID"),
    }

    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    created = {}
    orchestrator_spec = None

    # 1. Create journey agents first.
    for a in spec["agents"]:
        if a["role"] == "orchestrator":
            orchestrator_spec = a
            continue
        print(f"Creating agent {a['name']} ...")
        tools = build_tools(project, a.get("tools", []), ctx)
        agent = project.agents.create_agent(
            model=model, name=a["name"], instructions=a["instructions"], tools=tools or None)
        created[a["name"]] = agent.id
        print(f"  -> {agent.id}")

    # 2. Create the orchestrator with connected-agent tools.
    if orchestrator_spec:
        print(f"Creating orchestrator {orchestrator_spec['name']} ...")
        tools = build_tools(project, orchestrator_spec.get("tools", []), ctx)
        _add_connected_agents(tools, orchestrator_spec.get("connected_agents", []), created, spec)
        agent = project.agents.create_agent(
            model=model, name=orchestrator_spec["name"],
            instructions=orchestrator_spec["instructions"], tools=tools or None)
        created[orchestrator_spec["name"]] = agent.id
        print(f"  -> {agent.id}")

    OUT.write_text(json.dumps(created, indent=2), encoding="utf-8")
    print(f"\nCreated {len(created)} agents. IDs saved to {OUT.name}:")
    for name, aid in created.items():
        print(f"  {name}: {aid}")
    return 0


def _add_connected_agents(tools, names, created, spec):
    try:
        from azure.ai.agents.models import ConnectedAgentTool
    except Exception as ex:  # noqa: BLE001
        print(f"  (ConnectedAgentTool unavailable: {ex}; orchestrator will not auto-delegate)")
        return
    desc = {a["name"]: a.get("instructions", "")[:120] for a in spec["agents"]}
    for name in names:
        aid = created.get(name)
        if not aid:
            print(f"  ! connected agent {name} not created; skipping")
            continue
        tools.extend(ConnectedAgentTool(
            id=aid, name=name, description=desc.get(name, name)).definitions)
        print(f"  + connected agent: {name}")


if __name__ == "__main__":
    raise SystemExit(main())
