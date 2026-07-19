"""
Foundry client for the agent-desktop web app.

There is no single orchestrator agent. Instead, three independent journey agents
were deployed (see foundry/agents.generated.json):

    telco-BillingFirstBillAgent   - billing, invoices, first-bill, payments
    telco-CrossSellAgent          - new service, cross-sell / upsell, offers, bundles
    telco-ServiceRetentionAgent   - outages, service degradation, tickets, retention/credits

This module picks the best journey agent for each message with lightweight keyword
routing, then runs the message against that agent. If the Foundry endpoint or agent
ids are unavailable, it falls back to a local reply that summarizes the customer 360
profile so the app stays demoable without cloud agents.

Every chat() call returns a rich ``debug`` object (routing reasoning, timing, response
id, token usage, trace id) so the web app can show what it did and why.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
AGENTS_FILE = REPO / "foundry" / "agents.generated.json"

# Journey agent names as written by deploy_agents.py.
BILLING_AGENT = "telco-BillingFirstBillAgent"
CROSSSELL_AGENT = "telco-CrossSellAgent"
SERVICE_AGENT = "telco-ServiceRetentionAgent"
DEFAULT_AGENT = CROSSSELL_AGENT  # most general (has Fabric + Search + Web tools)

# Tools each agent carries (keep in sync with foundry/agents/agents.yaml).
AGENT_TOOLS: dict[str, list[str]] = {
    BILLING_AGENT: ["fabric_data_agent"],
    CROSSSELL_AGENT: ["fabric_data_agent", "azure_ai_search", "web"],
    SERVICE_AGENT: ["fabric_data_agent", "web"],
}

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

SHORT = {BILLING_AGENT: "Billing", CROSSSELL_AGENT: "CrossSell", SERVICE_AGENT: "ServiceRetention"}


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
    for name in (BILLING_AGENT, CROSSSELL_AGENT, SERVICE_AGENT):
        env_key = re.sub(r"[^A-Z0-9]", "", name.upper()) + "_AGENT_ID"
        if os.environ.get(env_key):
            ids[name] = os.environ[env_key]
    return ids


def route_detail(message: str, profile: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Pick the best journey agent and explain *why* (scores, matches, nudges)."""
    text = (message or "").lower()
    scores: dict[str, int] = {agent: 0 for agent, _ in _ROUTES}
    matched: dict[str, list[str]] = {agent: [] for agent, _ in _ROUTES}
    for agent, keywords in _ROUTES:
        hits = [kw for kw in keywords if kw in text]
        matched[agent] = hits
        scores[agent] = len(hits)

    nudges: list[str] = []
    if profile:
        if _truthy(profile.get("last_invoice_is_first_bill")):
            scores[BILLING_AGENT] += 1
            nudges.append("profile: first bill \u2192 Billing +1")
        if _truthy(profile.get("recent_outage_exposure")):
            scores[SERVICE_AGENT] += 1
            nudges.append("profile: recent outage \u2192 ServiceRetention +1")
        elif str(profile.get("risk_band", "")).lower() == "high":
            scores[SERVICE_AGENT] += 1
            nudges.append("profile: high churn risk \u2192 ServiceRetention +1")

    best = max(scores.values()) if scores else 0
    if best == 0:
        chosen = DEFAULT_AGENT
        reason = "no keyword or profile signal \u2192 default agent"
    else:
        chosen = next(a for a, _ in _ROUTES if scores.get(a, 0) == best)
        kw = matched.get(chosen, [])
        bits = []
        if kw:
            bits.append("keywords: " + ", ".join(kw[:6]))
        if any(SHORT[chosen] in x for x in nudges):
            bits.append("+ profile signal")
        reason = ("; ".join(bits) or "profile signal") + f" (score {best})"

    return {
        "chosen": chosen,
        "scores": scores,
        "matched": matched,
        "nudges": nudges,
        "reason": reason,
        "agent_tools": AGENT_TOOLS.get(chosen, []),
    }


def route(message: str, profile: Optional[dict[str, Any]] = None) -> str:
    return route_detail(message, profile)["chosen"]


def chat(message: str, profile: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    ids = _agent_ids()

    rd = route_detail(message, profile)
    agent_name = rd["chosen"]
    route_ms = (time.perf_counter() - t0) * 1000.0

    debug: dict[str, Any] = {
        "input_chars": len(message or ""),
        "profile_loaded": bool(profile),
        "context_included": bool(profile),
        "routing": rd,
        "agent_available": agent_name in ids,
        "timing_ms": {"route": round(route_ms, 1)},
        "spans": [{"name": "route", "ms": round(route_ms, 1)}],
        "response_id": None,
        "usage": None,
        "trace_id": None,
        "error": None,
        "app_insights": _app_insights_info(),
    }

    if endpoint and agent_name in ids:
        ta = time.perf_counter()
        try:
            meta: dict[str, Any] = {}
            reply = _run_foundry(endpoint, agent_name, message, profile, meta)
            call_ms = (time.perf_counter() - ta) * 1000.0
            debug["timing_ms"]["agent_call"] = round(call_ms, 1)
            debug["spans"].append({"name": f"agent:{SHORT.get(agent_name, agent_name)}",
                                   "ms": round(call_ms, 1)})
            debug["response_id"] = meta.get("response_id")
            debug["usage"] = meta.get("usage")
            debug["trace_id"] = meta.get("trace_id")
            debug["timing_ms"]["total"] = round((time.perf_counter() - t0) * 1000.0, 1)
            return {"mode": "foundry", "agent": agent_name, "reply": reply, "debug": debug}
        except Exception as ex:  # noqa: BLE001
            call_ms = (time.perf_counter() - ta) * 1000.0
            debug["timing_ms"]["agent_call"] = round(call_ms, 1)
            debug["error"] = f"{type(ex).__name__}: {ex}"
            debug["timing_ms"]["total"] = round((time.perf_counter() - t0) * 1000.0, 1)
            return {"mode": "foundry-error", "agent": agent_name,
                    "reply": f"(Foundry call failed: {ex})\n\n" + _local_reply(message, profile),
                    "debug": debug}

    if not endpoint:
        debug["error"] = "FOUNDRY_PROJECT_ENDPOINT not set (local mode)"
    elif agent_name not in ids:
        debug["error"] = f"agent '{agent_name}' not in agents.generated.json (local mode)"
    debug["timing_ms"]["total"] = round((time.perf_counter() - t0) * 1000.0, 1)
    return {"mode": "local", "agent": agent_name,
            "reply": _local_reply(message, profile), "debug": debug}


# --- OpenTelemetry export to App Insights (optional, best-effort) ----------------------
_OTEL_STATE: dict[str, Any] = {"init": False, "tracer": None}


def _ensure_otel():
    """Configure Azure Monitor OpenTelemetry once if a connection string is present."""
    if _OTEL_STATE["init"]:
        return _OTEL_STATE["tracer"]
    _OTEL_STATE["init"] = True
    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        return None
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry import trace
        configure_azure_monitor(connection_string=conn, logger_name="telco-app")
        _OTEL_STATE["tracer"] = trace.get_tracer("telco-agent-desktop")
    except Exception:  # noqa: BLE001
        _OTEL_STATE["tracer"] = None
    return _OTEL_STATE["tracer"]


def _app_insights_info() -> Optional[dict[str, str]]:
    name = os.environ.get("APP_INSIGHTS_NAME")
    sub = os.environ.get("AZURE_SUBSCRIPTION_ID")
    rg = os.environ.get("AZURE_RESOURCE_GROUP")
    if not name:
        return None
    info = {"name": name}
    if sub and rg:
        rid = (f"/subscriptions/{sub}/resourceGroups/{rg}/providers/"
               f"microsoft.insights/components/{name}")
        info["portal_url"] = f"https://portal.azure.com/#@/resource{rid}/searchV1"
    return info


def _run_foundry(endpoint, agent_name, message, profile, meta: dict[str, Any]) -> str:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    content = message
    if profile:
        content = (f"[Customer 360 context]\n{json.dumps(profile, default=str)}\n\n"
                   f"[Customer request]\n{message}")

    tracer = _ensure_otel()
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential(),
                              allow_preview=True)

    def _do() -> str:
        with project:
            openai_client = project.get_openai_client(agent_name=agent_name)
            response = openai_client.responses.create(input=content)
            meta["response_id"] = getattr(response, "id", None)
            usage = getattr(response, "usage", None)
            if usage is not None:
                meta["usage"] = {
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
            return _extract_text(response)

    if tracer is not None:
        try:
            with tracer.start_as_current_span("agent.chat") as span:
                span.set_attribute("telco.agent", agent_name)
                span.set_attribute("gen_ai.system", "azure_ai_foundry")
                ctx = span.get_span_context()
                meta["trace_id"] = format(ctx.trace_id, "032x")
                text = _do()
                if meta.get("response_id"):
                    span.set_attribute("telco.response_id", meta["response_id"])
                return text
        except Exception:  # noqa: BLE001
            return _do()
    return _do()


def _extract_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for c in getattr(item, "content", []) or []:
            t = getattr(c, "text", None)
            if isinstance(t, str):
                parts.append(t)
            elif t is not None and getattr(t, "value", None):
                parts.append(t.value)
    return "\n".join(parts) if parts else "(no assistant response)"


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
