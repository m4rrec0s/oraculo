#!/bin/bash
# Hermes Enterprise — proper entrypoint
# 1. Install missing deps  2. Setup profile  3. Generate config  4. Run gateway
set -euo pipefail

# Ensure pg8000 (read-only Cesto DB stats) is available for daily_summary.py
python3 -m pip install --quiet pg8000 >/dev/null 2>&1 || true

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; MAGENTA='\033[0;35m'; NC='\033[0m'
log()   { echo -e "${BLUE}[ENTERPRISE]${NC} $*"; }
ok()    { echo -e "${GREEN}[ENTERPRISE]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ENTERPRISE]${NC} $*"; }
err()   { echo -e "${RED}[ENTERPRISE]${NC} $*"; }

# ==================== CONFIG ====================
PROFILE="${ENTERPRISE_PROFILE:-atendimento}"
HERMES_HOME_BASE="${HERMES_HOME:-/home/hermes/.hermes}"
PROFILE_HOME="${HERMES_HOME_BASE}/profiles/${PROFILE}"
CONFIG_FILE="${PROFILE_HOME}/config.yaml"

# Model config — override via env vars
MODEL_PROVIDER="${MODEL_PROVIDER:-nvidia}"
MODEL_NAME="${MODEL_NAME:-nvidia/nemotron-3-super-120b-a12b}"
MODEL_BASE_URL="${MODEL_BASE_URL:-https://integrate.api.nvidia.com/v1}"
API_KEY_VAR="${API_KEY_VAR:-NVIDIA_API_KEY}"

log "Profile: ${MAGENTA}${PROFILE}${NC}"
log "Model:   ${MAGENTA}${MODEL_PROVIDER}/${MODEL_NAME}${NC}"

# ==================== 1. INSTALL DEPS ====================
log "Installing dependencies..."
pip install --quiet aiohttp 2>/dev/null && ok "aiohttp installed" || warn "aiohttp install failed (non-fatal)"

# ==================== 2. SETUP PROFILE ====================
# Skills: bundled skills only when ENTERPRISE_SKILLS=1 (e.g. admin).
# Otherwise the profile stays minimal (persona has its own skills).
SKILLS_FLAG="--no-skills"
if [[ "${ENTERPRISE_SKILLS:-0}" == "1" ]]; then
    SKILLS_FLAG=""
fi

# PROFILE_BIND=1 → profile dir is pre-mounted (shared volume from Managing
# Profile). profile create refuses a pre-existing mount dir, so build manually.
PROFILE_BIND="${PROFILE_BIND:-0}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    log "Creating profile: ${PROFILE}"
    mkdir -p "${PROFILE_HOME}/skills" "${HERMES_HOME_BASE}/.local/bin"
    if [[ "${PROFILE_BIND}" == "1" ]]; then
        touch "${PROFILE_HOME}/.no-bundled-skills"
    else
        python -m hermes_cli.main profile create "${PROFILE}" ${SKILLS_FLAG} 2>/dev/null || true
    fi
fi

# Ensure wrapper exists (manual — works for volume-backed profiles too)
if [[ ! -f "${HERMES_HOME_BASE}/.local/bin/${PROFILE}" ]]; then
    mkdir -p "${HERMES_HOME_BASE}/.local/bin"
    cat > "${HERMES_HOME_BASE}/.local/bin/${PROFILE}" << WRAPEOF
#!/bin/bash
export HERMES_HOME="${PROFILE_HOME}"
exec python3 /app/hermes -p ${PROFILE} "\$@"
WRAPEOF
    chmod +x "${HERMES_HOME_BASE}/.local/bin/${PROFILE}"
fi

# Export profile — HERMES_HOME must point to profile dir for config resolution
export HERMES_HOME="${PROFILE_HOME}"
export PATH="${HERMES_HOME_BASE}/.local/bin:${PATH}"

log "HERMES_HOME: ${MAGENTA}${HERMES_HOME}${NC}"

# ==================== 3. GENERATE CONFIG ====================
if [[ ! -f "${CONFIG_FILE}" ]]; then
    log "Generating config for ${PROFILE}..."
    mkdir -p "$(dirname "${CONFIG_FILE}")"

    # Determine provider config
    # "openai" is aliased to "openrouter" by hermes — use "custom" with base_url for direct OpenAI
    PROVIDER_CONFIG="${MODEL_PROVIDER}"
    if [[ "${MODEL_PROVIDER}" == "openai" ]]; then
        PROVIDER_CONFIG="custom"
    fi

    # Minimal config when ENTERPRISE_MINIMAL=1 (default for personas):
    # restrict toolsets via DISABLED_TOOLSETS env (comma-separated) and keep
    # max_iterations low. Otherwise use the standard config.
    if [[ "${ENTERPRISE_MINIMAL:-1}" == "1" ]]; then
        DISABLED_BLOCK=""
        IFS=',' read -ra TS <<< "${DISABLED_TOOLSETS:-}"
        for ts in "${TS[@]}"; do
            ts="$(echo -n "$ts" | xargs)"
            [[ -n "$ts" ]] && DISABLED_BLOCK="${DISABLED_BLOCK}    - ${ts}\n"
        done
        cat > "${CONFIG_FILE}" << YAMLEOF
# Hermes Enterprise — ${PROFILE} config (minimal)

model:
  provider: ${PROVIDER_CONFIG}
  default: ${MODEL_NAME}
  base_url: ${MODEL_BASE_URL}

agent:
  name: ${AGENT_NAME:-Hermes}
  max_iterations: ${ENTERPRISE_MAX_ITER:-5}
  tool_use_enforcement: auto
$([[ -n "${DISABLED_BLOCK}" ]] && printf "  disabled_toolsets:\n${DISABLED_BLOCK}")
gateway:
  platforms: []

api_server:
  enabled: true
  host: ${API_SERVER_HOST:-0.0.0.0}
  port: ${API_SERVER_PORT:-8000}
YAMLEOF
    else
        cat > "${CONFIG_FILE}" << YAMLEOF
# Hermes Enterprise — ${PROFILE} config

model:
  provider: ${PROVIDER_CONFIG}
  default: ${MODEL_NAME}
  base_url: ${MODEL_BASE_URL}

agent:
  name: ${AGENT_NAME:-Hermes}
  max_iterations: ${ENTERPRISE_MAX_ITER:-15}
  tool_use_enforcement: auto

gateway:
  platforms: []

api_server:
  enabled: true
  host: ${API_SERVER_HOST:-0.0.0.0}
  port: ${API_SERVER_PORT:-8000}
YAMLEOF
    fi
    ok "Config written to ${CONFIG_FILE}"
else
    log "Config exists: ${CONFIG_FILE}"
fi

# ==================== 3b. SOUL.MD (persona) ====================
# Persona comes from the Hermes default (no custom SOUL) unless an optional
# template ships at enterprise/soul/<PROFILE>.md. Admin edits it later via
# the EditService (edit_persona). Nothing hardcoded per-persona here.
SOUL_FILE="${PROFILE_HOME}/SOUL.md"
if [[ ! -f "${SOUL_FILE}" ]]; then
    if [[ -f "/home/hermes/enterprise/soul/${PROFILE}.md" ]]; then
        cp "/home/hermes/enterprise/soul/${PROFILE}.md" "${SOUL_FILE}"
        ok "SOUL.md seeded from enterprise/soul/${PROFILE}.md"
    else
        # No template → Hermes default persona (empty SOUL, base system prompt).
        log "No SOUL.md template for ${PROFILE} — using Hermes default persona."
    fi
fi

# ==================== 3b-2. ENTERPRISE CUSTOM SKILLS ====================
# Every profile gets its enterprise custom skills if a dir ships for it.
if [[ -d "/home/hermes/enterprise/skills/${PROFILE}" ]]; then
    cp -rf "/home/hermes/enterprise/skills/${PROFILE}/"* "${PROFILE_HOME}/skills/" 2>/dev/null || true
    ok "Enterprise custom skills copied for ${PROFILE}"
fi

# Persist HERMES_HOME for docker exec sessions (interactive bash sources .bashrc)
if ! grep -q "HERMES_HOME=${PROFILE_HOME}" /home/hermes/.bashrc 2>/dev/null; then
    echo "export HERMES_HOME=\"${PROFILE_HOME}\"" >> /home/hermes/.bashrc
fi
if [ -f /home/hermes/.profile ] && ! grep -q "HERMES_HOME=${PROFILE_HOME}" /home/hermes/.profile 2>/dev/null; then
    echo "export HERMES_HOME=\"${PROFILE_HOME}\"" >> /home/hermes/.profile
fi

# ==================== 3c. DASHBOARD (optional) ====================
if [[ "${DASHBOARD_ENABLED:-false}" == "true" ]]; then
    DASH_PORT="${DASHBOARD_PORT:-9119}"
    DASH_HOST="${DASHBOARD_HOST:-0.0.0.0}"
    log "Starting Hermes dashboard on ${DASH_HOST}:${DASH_PORT}..."
    if [ -d "${HERMES_HOME_BASE}/hermes_cli/web_dist" ] || [ -d "/app/hermes_cli/web_dist" ]; then
        # TUI (embedded Chat tab) needs the prebuilt bundle + node on PATH
        export HERMES_TUI_DIR=/app/ui-tui
        export PATH="/home/hermes/.hermes/node/bin:${PATH}"
        nohup python -m hermes_cli.main -p "${PROFILE}" dashboard \
            --port "${DASH_PORT}" --host "${DASH_HOST}" --no-open --insecure --skip-build --isolated \
            > /tmp/dashboard.log 2>&1 &
        ok "Dashboard starting on port ${DASH_PORT} (profile: ${PROFILE})"
    else
        warn "Dashboard web_dist not found — skipping dashboard start"
    fi
fi

# ==================== 3d. MIGRATION (sessões Postgres) ====================
# Roda no boot de todo container (idempotente). Garante que as tabelas de
# sessão existam e tenham a coluna 'persona' (multi-persona) antes do gateway.
if [[ -n "${DATABASE_URL:-}" ]]; then
    log "Applying session schema migration (DATABASE_URL)..."
    PYTHONPATH="/app:${PYTHONPATH:-}" python - << 'PYEOF'
import asyncio
import sys
sys.path.insert(0, "/app")
try:
    from enterprise.mcp.ana_sessions import init_schema
    asyncio.run(init_schema())
    print("[ENTERPRISE] session schema migrated OK")
except Exception as exc:
    print(f"[ENTERPRISE] session schema migration skipped: {exc}", file=sys.stderr)
PYEOF
else
    warn "DATABASE_URL não definido — pulando migration de sessões."
fi

# ==================== 4. RUN ====================
log "Starting Hermes gateway..."
exec python -m hermes_cli.main gateway run "$@"
