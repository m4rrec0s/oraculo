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

# ==================== 1b. ANA SESSIONS SCHEMA (Hermes PG dedicado) ====================
# Cria ana_sessions / ana_messages no Postgres dedicado do Hermes (HERMES_PG_*).
# Idempotente (CREATE IF NOT EXISTS). Roda em admin E atendimento.
if [[ -n "${HERMES_PG_HOST:-}" ]]; then
  log "Ensuring Ana sessions schema on ${HERMES_PG_HOST}..."
  python3 - <<'PYEOF'
import os, sys
try:
    import pg8000
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pg8000"], check=False)
    try:
        import pg8000
    except Exception:
        pg8000 = None
if pg8000 is None:
    print("[ENTERPRISE] pg8000 unavailable — skipping ana schema")
    sys.exit(0)
sql_path = "/home/hermes/enterprise/mcp/ana_sessions.sql"
if not os.path.exists(sql_path):
    print("[ENTERPRISE] ana_sessions.sql not found — skipping")
    sys.exit(0)
try:
    conn = pg8000.connect(
        host=os.environ.get("HERMES_PG_HOST"),
        port=int(os.environ.get("HERMES_PG_PORT", "5432")),
        database=os.environ.get("HERMES_PG_DATABASE", "hermes_enterprise"),
        user=os.environ.get("HERMES_PG_USER", "hermes"),
        password=os.environ.get("HERMES_PG_PASSWORD", ""),
    )
    with open(sql_path) as f:
        sql = f.read()
    cur = conn.cursor()
    for stmt in sql.split(";"):
        s = stmt.strip()
        if s:
            cur.execute(s)
    conn.commit()
    cur.close()
    conn.close()
    print("[ENTERPRISE] ana_sessions schema ensured")
except Exception as e:
    print(f"[ENTERPRISE] WARN: ana schema ensure failed: {e}")
PYEOF
fi

# ==================== 2. SETUP PROFILE ====================
# Admin gets full bundled skills; atendimento stays minimal (Ana has own persona)
SKILLS_FLAG="--no-skills"
if [[ "${PROFILE}" == "admin" ]]; then
    SKILLS_FLAG=""
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
    log "Creating profile: ${PROFILE}"
    mkdir -p "${PROFILE_HOME}/skills" "${HERMES_HOME_BASE}/.local/bin"
    if [[ "${PROFILE}" == "atendimento" ]]; then
        # Atendimento profile lives on a shared volume (Managing Profile).
        # profile create refuses the pre-existing mount dir, so build it manually.
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

    # Atendimento gets minimal config — only clarify + web tools
    if [[ "${PROFILE}" == "atendimento" ]]; then
        cat > "${CONFIG_FILE}" << YAMLEOF
# Hermes Enterprise — atendimento config (minimal)

model:
  provider: ${PROVIDER_CONFIG}
  default: ${MODEL_NAME}
  base_url: ${MODEL_BASE_URL}

agent:
  name: ${AGENT_NAME:-Ana}
  max_iterations: 5
  tool_use_enforcement: auto
  disabled_toolsets:
    - hermes-cli
    - hermes-telegram
    - hermes-discord
    - hermes-slack
    - hermes-whatsapp
    - hermes-email
    - hermes-sms
    - hermes-matrix
    - hermes-mattermost
    - hermes-dingtalk
    - hermes-wecom
    - hermes-feishu
    - hermes-qqbot
    - hermes-signal
    - hermes-bluebubbles
    - hermes-weixin
    - hermes-yuanbao
    - hermes-acp
    - hermes-api-server
    - hermes-webhook
    - hermes-homeassistant
    - hermes-cron
    - browser
    - code_execution
    - coding
    - computer_use
    - debugging
    - delegation
    - file
    - image_gen
    - kanban
    - moa
    - spotify
    - terminal
    - todo
    - tts
    - video
    - video_gen
    - vision
    - x_search
    - homeassistant
    - cronjob

gateway:
  platforms: []

api_server:
  enabled: true
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
  max_iterations: 15
  tool_use_enforcement: auto

gateway:
  platforms: []

api_server:
  enabled: true
YAMLEOF
    fi
    ok "Config written to ${CONFIG_FILE}"
else
    log "Config exists: ${CONFIG_FILE}"
fi

# ==================== 3b. SOUL.MD (persona) ====================
SOUL_FILE="${PROFILE_HOME}/SOUL.md"
if [[ "${PROFILE}" == "atendimento" && ! -f "${SOUL_FILE}" ]]; then
    if [[ -f "/home/hermes/enterprise/soul/ana.md" ]]; then
        cp "/home/hermes/enterprise/soul/ana.md" "${SOUL_FILE}"
        ok "Ana SOUL.md seeded from enterprise/soul/ana.md"
    else
        log "Writing Ana persona to SOUL.md..."
        cat > "${SOUL_FILE}" << 'SOULEOF'
# Ana — Atendente Cesto d'Amore

Você é **Ana**, atendente da Cesto d'Amore — a melhor loja de cestas personalizadas e presentes de Campina Grande-PB.

## Identidade

- **Nome:** Ana
- **Empresa:** Cesto d'Amore (cestas, flores, presentes personalizados)
- **Tom:** Informal, calorosa, como amiga prestativa. Use abreviações naturais: vc, pra, tá, tb.
- **Idioma:** Português brasileiro.
- **Emojis:** Máximo 2 por mensagem: 💕 🎁 ✅ 🥰 😊
- **NUNCA** mencione que é IA, robô ou assistente virtual.
- **NUNCA** comece respostas negativas com "Claro" — vá direto ao ponto.

## Regras de Ouro (INVIOLÁVEIS)

### 1. Redirecionamento para o Site

**Toda intenção de compra → site.** Nunca feche venda diretamente.

- "Toda compra é pelo site, tá? Lá vc vê todos os produtos, preços e faz o pedido com calma! 🎁 https://www.cestodamore.com.br"

### 2. O que NÃO fazer

- Inventar ou sugerir composições de cestas
- Fazer curadoria ("te recomendo essa cesta...")
- Criar pacotes personalizados
- Passar preços sem o cliente ver no site
- Coletar dados para fechar pedido (endereço, pagamento, data)
- Atuar como vendedora ativa

### 3. O que PODE fazer

- Tirar dúvidas gerais (horário, entrega, produção, personalização)
- Informar regras da loja
- Orientar sobre formas de entrega e prazos
- Encaminhar para páginas específicas do site

## Autoaprendizado (recurso interno do Hermes)
Use a memoria e a skill autoaprendizado-ana para evoluir a cada atendimento:
registre duvidas recorrentes e respostas que funcionaram, e consolide padroes em FAQs.
Nunca quebre as Regras de Ouro ao aprender.
SOULEOF
        ok "SOUL.md written"
    fi
fi

# ==================== 3b-2. ADMIN SOUL + ENTERPRISE CUSTOM SKILLS ====================
# Admin gets a business-manager persona; both profiles get enterprise custom skills
if [[ "${PROFILE}" == "admin" && ! -f "${SOUL_FILE}" ]]; then
    if [[ -f "/home/hermes/enterprise/soul/admin.md" ]]; then
        cp "/home/hermes/enterprise/soul/admin.md" "${SOUL_FILE}"
        ok "Admin SOUL.md written from enterprise template"
    fi
fi

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

# ==================== 4. RUN ====================
log "Starting Hermes gateway..."
exec python -m hermes_cli.main "$@" gateway run
