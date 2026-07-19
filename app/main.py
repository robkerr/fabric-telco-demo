"""
Agent-desktop web app (FastAPI).

Endpoints:
  GET  /                       -> agent desktop UI
  GET  /api/health            -> mode (live/local)
  GET  /api/search?q=...      -> customer lookup
  GET  /api/profile/{id}      -> customer_360 profile (fetch-on-contact)
  POST /api/chat              -> auto-route a message to the best Foundry journey agent

Run locally:
  uvicorn main:app --reload --port 8000   (from the app/ folder)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load repo .env for local runs (App Service injects app settings directly).
REPO = Path(__file__).resolve().parent.parent
_envfile = REPO / ".env"
if _envfile.exists():
    for _line in _envfile.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"'))

import agent_client  # noqa: E402
import data_access  # noqa: E402

app = FastAPI(title="Telco Agent Desktop")
STATIC = Path(__file__).resolve().parent / "static"


class ChatRequest(BaseModel):
    message: str
    customer_id: str | None = None


@app.get("/api/health")
def health():
    return {"status": "ok", "data_mode": data_access.mode()}


@app.get("/api/search")
def search(q: str):
    return {"results": data_access.search_customers(q)}


@app.get("/api/profile/{customer_id}")
def profile(customer_id: str):
    p = data_access.get_profile(customer_id)
    if not p:
        raise HTTPException(status_code=404, detail="Customer not found")
    return p


@app.post("/api/chat")
def chat(req: ChatRequest):
    prof = data_access.get_profile(req.customer_id) if req.customer_id else None
    return agent_client.chat(req.message, prof)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
