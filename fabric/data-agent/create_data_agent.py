"""
Create, configure, and publish the Telco Fabric Data Agent from config.yaml.

Uses the fabric-data-agent-sdk (management plane). Runs both inside a Fabric notebook
(auth is automatic) and outside Fabric (authenticates via Azure CLI or a service
principal from environment variables).

Environment (loaded from repo .env by scripts/30_create_data_agent.ps1):
    FABRIC_WORKSPACE_ID     target workspace
    FABRIC_LAKEHOUSE_NAME   lakehouse artifact name (default TelcoLakehouse)
    SPN_APP_ID / SPN_CLIENT_SECRET / SPN_TENANT_ID   optional service principal

Writes DATA_AGENT_ARTIFACT_ID and DATA_AGENT_MCP_ENDPOINT back to .env when possible.

Docs: https://learn.microsoft.com/fabric/data-science/fabric-data-agent-sdk
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CONFIG = HERE / "config.yaml"
ENV_FILE = REPO / ".env"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def set_env_file(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, found = [], False
    for ln in lines:
        if ln.startswith(f"{key}="):
            out.append(f"{key}={value}"); found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def authenticate_if_outside_fabric() -> None:
    """Inside a Fabric notebook auth is automatic; outside we set a default credential."""
    try:
        import notebookutils  # noqa: F401  (present only inside Fabric)
        return
    except Exception:
        pass

    from fabric.analytics.environment.credentials import (
        SetFabricAnalyticsDefaultTokenCredentialsGlobally,
    )

    app_id = os.environ.get("SPN_APP_ID")
    secret = os.environ.get("SPN_CLIENT_SECRET")
    tenant = os.environ.get("SPN_TENANT_ID")
    if app_id and secret and tenant:
        from azure.identity import ClientSecretCredential
        cred = ClientSecretCredential(tenant_id=tenant, client_id=app_id, client_secret=secret)
        print("Authenticating with service principal.")
    else:
        from azure.identity import AzureCliCredential
        cred = AzureCliCredential()
        print("Authenticating with Azure CLI credential.")
    SetFabricAnalyticsDefaultTokenCredentialsGlobally(cred)


def main() -> int:
    load_env_file(ENV_FILE)
    workspace_id = os.environ.get("FABRIC_WORKSPACE_ID")
    if not workspace_id or workspace_id.startswith("00000000"):
        print("ERROR: FABRIC_WORKSPACE_ID is not set in .env", file=sys.stderr)
        return 1

    with open(CONFIG, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    authenticate_if_outside_fabric()

    from fabric.dataagent.client import create_data_agent

    name = cfg["name"]
    print(f"Creating/opening data agent '{name}' in workspace {workspace_id} ...")
    agent = create_data_agent(data_agent_name=name, workspace_id=workspace_id)

    # 1. Global AI instructions
    agent.update_settings(ai_instructions=cfg["ai_instructions"])
    print("Applied AI instructions.")

    # 2. Data sources
    for ds_cfg in cfg.get("datasources", []):
        artifact = ds_cfg["artifact"]
        print(f"Adding datasource '{artifact}' ...")
        ds = agent.add_staging_datasource(
            artifact_name_or_id=artifact,
            workspace_id_or_name=workspace_id,
        )
        # Datasource-level instructions (method name varies by SDK version -> best effort)
        _best_effort_ds_instructions(ds, ds_cfg.get("instructions"))
        _best_effort_example_queries(ds, agent, cfg.get("example_queries", []))

    # 3. Publish
    agent.publish_staging(description=cfg.get("description", "Telco data agent publish"))
    print("Published data agent.")

    # 4. Record artifact id + MCP endpoint if discoverable
    artifact_id = _discover_artifact_id(agent)
    if artifact_id:
        mcp = (f"https://api.fabric.microsoft.com/v1/mcp/workspaces/{workspace_id}"
               f"/dataagents/{artifact_id}/agent")
        set_env_file(ENV_FILE, "DATA_AGENT_ARTIFACT_ID", artifact_id)
        set_env_file(ENV_FILE, "DATA_AGENT_MCP_ENDPOINT", mcp)
        print(f"DATA_AGENT_ARTIFACT_ID = {artifact_id}")
        print(f"DATA_AGENT_MCP_ENDPOINT = {mcp}")
    else:
        print("NOTE: could not auto-discover the data agent id; copy it from the "
              "Model Context Protocol tab in the agent settings into .env.")
    return 0


def _best_effort_ds_instructions(ds, instructions):
    if not instructions:
        return
    for method in ("update_configuration", "update_settings", "set_instructions"):
        fn = getattr(ds, method, None)
        if callable(fn):
            try:
                fn(instructions=instructions)
                print(f"  datasource instructions applied via {method}().")
                return
            except Exception:  # noqa: BLE001
                continue
    print("  (skipped datasource-level instructions; not supported by this SDK version)")


def _best_effort_example_queries(ds, agent, examples):
    if not examples:
        return
    # Try a few known shapes across SDK versions.
    for target in (ds, agent):
        for method in ("add_example_queries", "add_example_query"):
            fn = getattr(target, method, None)
            if not callable(fn):
                continue
            try:
                if method.endswith("queries"):
                    fn([(e["question"], e["query"]) for e in examples])
                else:
                    for e in examples:
                        fn(e["question"], e["query"])
                print(f"  {len(examples)} example queries applied via {method}().")
                return
            except Exception:  # noqa: BLE001
                continue
    print("  (skipped example queries; not supported by this SDK version)")


def _discover_artifact_id(agent):
    for attr in ("id", "artifact_id", "data_agent_id"):
        val = getattr(agent, attr, None)
        if val:
            return str(val)
    # some SDKs expose a nested object
    for attr in ("artifact", "metadata", "properties"):
        obj = getattr(agent, attr, None)
        if obj is not None:
            for k in ("id", "artifact_id"):
                v = getattr(obj, k, None)
                if v:
                    return str(v)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
