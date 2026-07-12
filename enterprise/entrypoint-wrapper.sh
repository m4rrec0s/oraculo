#!/bin/bash
# Enterprise startup wrapper — installs missing deps then runs gateway
set -euo pipefail

echo "[ENTERPRISE-WRAPPER] Installing API server dependencies..."
pip install --quiet aiohttp 2>/dev/null || uv pip install --quiet aiohttp 2>/dev/null || true

echo "[ENTERPRISE-WRAPPER] Starting gateway..."
exec python -m hermes_cli.main gateway run
