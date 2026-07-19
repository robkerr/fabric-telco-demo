"""
Foundry client for the agent-desktop web app.

There is no single orchestrator agent. Instead, three independent journey agents
were deployed (see foundry/agents.generated.json):

    BillingFirstBillAgent   - billing, invoices, first-bill, payments
    CrossSellAgent          - new service, cross-sell / upsell, offers, bundles
    ServiceRetentionAgent   - outages, service degradation, tickets, retention/credits

This module picks the best journey agent for each message with lightweight keyword
routing, then runs the message against that agent. If the Foundry endpoint or agent
ids are unavailable, it falls back to a local reply that summarizes the customer 360
profile so the app stays demoable without cloud agents.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
AGENTS_FILE = REPO / "foundry" / "agents.generated.json"

# Journey agent names as written by deploy_agents.py.
BILLING_AGENT = "BillingFirstBillAgent"
CROSSSELL_AGENT = "CrossSellAgent"
SERVICE_AGENT = "ServiceRetentionAgent"
DEFAULT_AGENT = CROSSSELL_AGENT  # most general (has Fabric + Search + Web tools)

# Keyword signals per journey. Journey with the most matches wins; ties fall back
# to _ROUTES order, then DEFAULT_AGENT when nothing matches.
_ROUTES: list[tuple[str, list[str]]] = [
    (BILLING_AGENT, [
        "bill", "billing", "invoice", "charge", "charged", "payment", "pay",
        "balance", "due", "refund", "overcharge", "first bill", "statement",
        "autopay", "late fee", "proration", "activation fee",
    ]),
    (SERVICE_AGENT, [
        "outage", "down", "slow", "degrad", "latency", "packet", "drop",
        "no service", "not working", "ticket", "work order", "technician",
        "appointment", "cancel", "cancellation", "disconnect", "retention",
        "leave", "switch", "credit", "compensat", "reliab", "speed issue",
    ]),
    (CROSSSELL_AGENT, [
        "add", "upgrade", "cross-sell", "crosssell", "upsell", "bundle",
        "offer", "promo", "promotion", "deal", "new service", "new product",
        "mobile", "internet", "tv", "phone line", "plan", "recommend",
        "discount", "save", "eligible",
    ]),
]


def _agent_ids() -> dict[str, str]:
    """Return {agent_name: agent_id} from agents.generated.json + env overrides."""
    ids: dict[str, str] = {}
    if AGENTS_FILE.exists():
        try:
            data = json.loads(AGENTS_FILE.read_text(encoding="utf-8"))
            for name, entry in data.items():
                if isinstance(entry, dict) and entry.get("id"):
                    ids[name] = entry["id"]
                elif isinstance(entry, str):
                    ids[name] = entry
        except Exception:  # noqa: BLE001
            pass
    # Per-agent env overrides, e.g. BILLINGFIRSTBILLAGENT_AGENT_ID
    for name in (BILLING_AGENT, CROSSSELL_AGENT, SERVICE_AGENT):
        env_key = re.sub(r"[^A-Z0-9]", "", name.upper()) + "_AGENT_ID"
        if os.environ.get(env_key):
            ids[name] = os.environ[env_key]
    return ids


def route(message: str, profile: Optional[dict[str, Any]] = None) -> str:
    """Pick the best journey agent name for a message (+ optional 360 profile)."""
    text = (message or "").lower()
    scores: dict[str, int] = {agent: 0 for agent, _ in _ROUTES}
    for agent, keywords in _ROUTES:
        scores[agent] = sum(1 for kw in keywords if kw in text)

    # Profile-driven nudges when the message is ambiguous.
    if profile:
        if _truthy(profile.get("last_invoice_is_first_bill")):
            scores[BILLING_AGENT] += 1
        if _truthy(profile.get("recent_outage_exposure")) or \
                str(profile.get("risk_band", "")).lower() == "high":
            scores[SERVICE_AGENT] += 1

    best = max(scores.values()) if scores else 0
    if best == 0:
        return DEFAULT_AGENT
    # Deterministic tie-break in _ROUTES order.
    for agent, _ in _ROUTES:
        if scores.get(agent, 0) == best:
            return agent
    return DEFAULT_AGENT


def chat(message: str, profile: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    ids = _agent_ids()
    agent_name = route(message, profile)
    agent_id = ids.get(agent_name)
    if endpoint and agent_id:
        try:
            reply = _run_foundry(endpoint, agent_id, message, profile)
            return {"mode": "foundry", "agent": agent_name, "reply": reply}
        except Exception as ex:  # noqa: BLE001
            return {"mode": "foundry-error", "agent": agent_name,
                    "reply": f"(Foundry call failed: {ex})\n\n" + _local_reply(message, profile)}
    return {"mode": "local", "agent": agent_name, "reply": _local_reply(message, profile)}


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


def _truthy(v) -> bool:
    return v in (True, "True", 1, "1")


def _local_reply(message: str, profile: Optional[dict[str, Any]]) -> str:
    if not profile:
        return ("I don't have a customer profile loaded. Search for a customer first, then "
                "ask your question. (Running in local demo mode — deploy the Foundry agents "
                "for full AI responses.)")
    name = f"{profile.get('first_name','')} {profile.get('last_name','')}".strip()
    lines = [f"Here's what I can see for {name} (local demo mode):"]
    if _truthy(profile.get("last_invoice_is_first_bill")):
        lines.append(f"- This is their FIRST bill: ${profile.get('last_invoice_amount','?')} "
                     f"(includes one-time activation + proration).")
    if profile.get("open_balance") not in ("", 0, "0", None):
        lines.append(f"- Open balance: ${profile.get('open_balance')}.")
    if str(profile.get("risk_band", "")).lower() == "high":
        lines.append(f"- HIGH churn risk ({profile.get('churn_top_reason','')}). "
                     "Consider a retention/loyalty credit.")
    if _truthy(profile.get("recent_outage_exposure")):
        lines.append("- Recent outage in their area — a service credit may apply.")
    if profile.get("top_crosssell_product"):
        lines.append(f"- Cross-sell opportunity: {profile.get('top_crosssell_product')} "
                     f"(score {profile.get('top_crosssell_score','')}).")
    lines.append(f"\nYou asked: \"{message}\"")
    return "\n".join(lines)
