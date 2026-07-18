"""
Foundry orchestrator client for the agent-desktop web app.

If the Foundry project endpoint and the deployed orchestrator agent id are available,
run the message against the orchestrator. Otherwise fall back to a helpful local reply
that summarizes the customer's 360 profile so the app is demoable without cloud agents.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
AGENTS_FILE = REPO / "foundry" / "agents.generated.json"
ORCHESTRATOR_NAME = "TelcoOrchestrator"


def _orchestrator_id() -> Optional[str]:
    if os.environ.get("ORCHESTRATOR_AGENT_ID"):
        return os.environ["ORCHESTRATOR_AGENT_ID"]
    if AGENTS_FILE.exists():
        try:
            return json.loads(AGENTS_FILE.read_text(encoding="utf-8")).get(ORCHESTRATOR_NAME)
        except Exception:  # noqa: BLE001
            return None
    return None


def chat(message: str, profile: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    agent_id = _orchestrator_id()
    if endpoint and agent_id:
        try:
            return {"mode": "foundry", "reply": _run_foundry(endpoint, agent_id, message, profile)}
        except Exception as ex:  # noqa: BLE001
            return {"mode": "foundry-error",
                    "reply": f"(Foundry call failed: {ex})\n\n" + _local_reply(message, profile)}
    return {"mode": "local", "reply": _local_reply(message, profile)}


def _run_foundry(endpoint, agent_id, message, profile) -> str:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    agents = project.agents
    thread = agents.threads.create()
    content = message
    if profile:
        content = (f"[Customer 360 context]\n{json.dumps(profile, default=str)}\n\n"
                   f"[Customer request]\n{message}")
    agents.messages.create(thread_id=thread.id, role="user", content=content)
    run = agents.runs.create_and_process(thread_id=thread.id, agent_id=agent_id)
    if getattr(run, "status", "") == "failed":
        raise RuntimeError(getattr(run, "last_error", "run failed"))
    msgs = list(agents.messages.list(thread_id=thread.id))
    for m in msgs:
        if getattr(m, "role", "") == "assistant":
            parts = [t.text.value for t in getattr(m, "text_messages", []) if getattr(t, "text", None)]
            if parts:
                return "\n".join(parts)
    return "(no assistant response)"


def _local_reply(message: str, profile: Optional[dict[str, Any]]) -> str:
    if not profile:
        return ("I don't have a customer profile loaded. Search for a customer first, then "
                "ask your question. (Running in local demo mode — deploy the Foundry agents "
                "for full AI responses.)")
    name = f"{profile.get('first_name','')} {profile.get('last_name','')}".strip()
    lines = [f"Here's what I can see for {name} (local demo mode):"]
    if profile.get("last_invoice_is_first_bill") in (True, "True", 1, "1"):
        lines.append(f"- This is their FIRST bill: ${profile.get('last_invoice_amount','?')} "
                     f"(includes one-time activation + proration).")
    if profile.get("open_balance") not in ("", 0, "0", None):
        lines.append(f"- Open balance: ${profile.get('open_balance')}.")
    if str(profile.get("risk_band", "")).lower() == "high":
        lines.append(f"- HIGH churn risk ({profile.get('churn_top_reason','')}). "
                     "Consider a retention/loyalty credit.")
    if profile.get("recent_outage_exposure") in (True, "True", 1, "1"):
        lines.append("- Recent outage in their area — a service credit may apply.")
    if profile.get("top_crosssell_product"):
        lines.append(f"- Cross-sell opportunity: {profile.get('top_crosssell_product')} "
                     f"(score {profile.get('top_crosssell_score','')}).")
    lines.append(f"\nYou asked: \"{message}\"")
    return "\n".join(lines)
