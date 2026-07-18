#!/usr/bin/env bash
# App Service (Linux) startup command for the FastAPI agent desktop.
# Configure this as the App Service "Startup Command", or it is used by deploy_app.ps1.
python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
