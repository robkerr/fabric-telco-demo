"""
Deploy the Telco Foundry journey agents from foundry/agents/agents.yaml.

Creates independent agents in the Foundry project (azure-ai-projects >= 2.x API), each with
its own tools:
  - the Fabric Data Agent  (MicrosoftFabricPreviewTool, via a project connection)
  - Azure AI Search        (AzureAISearchTool / Foundry IQ knowledge source)
  - Web grounding          (BingGroundingTool / Web IQ)

Multi-agent orchestrator delegation is intentionally NOT wired here (the current SDK has no
ConnectedAgentTool; that needs preview workflow/A2A APIs). Each journey agent stands alone.

Environment (from repo .env):
    FOUNDRY_PROJECT_ENDPOINT   Foundry project endpoint
    FOUNDRY_MODEL              model *deployment* name (e.g. gpt-4.1)
    FABRIC_CONNECTION_NAME     project connection name for the Fabric data agent
    AI_SEARCH_CONNECTION_NAME  project connection name for Azure AI Search
    AI_SEARCH_INDEX            search index name (default 'telco-knowledge')
    BING_CONNECTION_NAME       optional Bing grounding connection for Web IQ

IMPORTANT: the Fabric data agent tool uses identity passthrough (On-Behalf-Of) and does NOT
support service principals. Run this signed in as a *user* (az login) who has access to the
Fabric data agent and its data sources.

Agent name/id/version are written to foundry/agents.generated.json.

Docs: https://learn.microsoft.com/azure/foundry/agents/how-to/tools/fabric
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


def resolve_connection_id(project, name, label):
    """Return a project connection's resource id by name, or None (logged)."""
    if not name:
        print(f"  - {label}: no connection name set; skipping.")
        return None
    try:
        conn = project.connections.get(name)
        cid = getattr(conn, "id", None)
        if cid:
            print(f"  + {label}: resolved connection '{name}'.")
            return cid
        print(f"  ! {label}: connection '{name}' has no id; skipping.")
    except Exception as ex:  # noqa: BLE001
        print(f"  ! {label}: could not resolve connection '{name}' ({ex}); skipping.")
    return None


def build_tools(tool_keys, ctx):
    """Build a list of tool objects for the given tool keys, best-effort."""
    from azure.ai.projects.models import (
        MicrosoftFabricPreviewTool, FabricDataAgentToolParameters, ToolProjectConnection,
        AzureAISearchTool, AzureAISearchToolResource, AISearchIndexResource,
        BingGroundingTool, BingGroundingSearchToolParameters, BingGroundingSearchConfiguration,
    )
    tools = []
    for key in tool_keys:
        if key == "fabric_data_agent" and ctx.get("fabric_conn_id"):
            tools.append(MicrosoftFabricPreviewTool(
                fabric_dataagent_preview=FabricDataAgentToolParameters(
                    project_connections=[ToolProjectConnection(
                        project_connection_id=ctx["fabric_conn_id"])])))
            print("    + Fabric data agent tool")
        elif key == "azure_ai_search" and ctx.get("search_conn_id"):
            tools.append(AzureAISearchTool(
                azure_ai_search=AzureAISearchToolResource(
                    indexes=[AISearchIndexResource(
                        project_connection_id=ctx["search_conn_id"],
                        index_name=ctx["search_index"])])))
            print("    + Azure AI Search tool")
        elif key == "web" and ctx.get("bing_conn_id"):
            tools.append(BingGroundingTool(
                bing_grounding=BingGroundingSearchToolParameters(
                    search_configurations=[BingGroundingSearchConfiguration(
                        project_connection_id=ctx["bing_conn_id"])])))
            print("    + Web (Bing grounding) tool")
        elif key in ("fabric_data_agent", "azure_ai_search", "web"):
            print(f"    - {key}: connection unavailable; tool skipped")
    return tools


def main() -> int:
    load_env_file(REPO / ".env")
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        print("ERROR: FOUNDRY_PROJECT_ENDPOINT not set (Phase 2).", file=sys.stderr)
        return 1

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    model = os.environ.get("FOUNDRY_MODEL", spec.get("model", "gpt-4.1"))

    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())

    print("Resolving project connections...")
    ctx = {
        "fabric_conn_id": resolve_connection_id(
            project, os.environ.get("FABRIC_CONNECTION_NAME"), "Fabric"),
        "search_conn_id": resolve_connection_id(
            project, os.environ.get("AI_SEARCH_CONNECTION_NAME"), "AI Search"),
        "bing_conn_id": resolve_connection_id(
            project, os.environ.get("BING_CONNECTION_NAME"), "Web/Bing"),
        "search_index": os.environ.get("AI_SEARCH_INDEX", "telco-knowledge"),
    }

    # Create the journey agents (independent; no orchestrator delegation).
    created = {}
    for a in spec["agents"]:
        if a.get("role") != "journey":
            continue
        name = a["name"]
        print(f"\nCreating agent {name} (model={model}) ...")
        tools = build_tools(a.get("tools", []), ctx)
        try:
            version = project.agents.create_version(
                agent_name=name,
                definition=PromptAgentDefinition(
                    model=model,
                    instructions=a["instructions"],
                    tools=tools or None,
                ),
            )
            created[name] = {"id": getattr(version, "id", None),
                             "version": getattr(version, "version", None)}
            print(f"  -> id={created[name]['id']} version={created[name]['version']}")
        except Exception as ex:  # noqa: BLE001
            print(f"  ! failed to create {name}: {ex}")

    if created:
        OUT.write_text(json.dumps(created, indent=2), encoding="utf-8")
        print(f"\nCreated {len(created)} agent(s). Details written to {OUT.name}.")
    else:
        print("\nNo agents were created.")
        return 1

    # Retire legacy agent names (e.g. renamed to the telco_ prefix). Best-effort.
    retire = [n for n in spec.get("retire", []) if n not in created]
    if retire:
        print("\nRetiring legacy agents...")
        for name in retire:
            try:
                project.agents.delete(agent_name=name)
                print(f"  - deleted {name}")
            except Exception as ex:  # noqa: BLE001
                print(f"  . skip {name} ({ex})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
