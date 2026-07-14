#!/bin/bash
# Easypanel Provisioning Wrapper
# 
# Este script carrega .env e executa o provisioning do Easypanel
# automaticamente, sem precisar fazer `set -a && source .env && set +a` manualmente.
#
# USO:
#   ./scripts/provision-easypanel.sh          # Provisioning normal
#   ./scripts/provision-easypanel.sh --dry-run  # Teste (sem fazer nada)
#   ./scripts/provision-easypanel.sh --help     # Ajuda
#

set -euo pipefail

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Funções de logging
log()   { echo -e "${BLUE}[PROVISION]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ============================================================================
# HELPERS
# ============================================================================

show_help() {
  cat << 'EOF'
Easypanel Provisioning Script

USAGE:
  ./scripts/provision-easypanel.sh          # Provisioning normal
  ./scripts/provision-easypanel.sh --dry-run  # Teste (sem fazer nada)
  ./scripts/provision-easypanel.sh --help     # Esta mensagem

REQUIREMENTS:
  - .env file in the project root with:
    * EASYPANEL_URL
    * EASYPANEL_TOKEN
    * EASYPANEL_PROJECT_NAME (opcional, padrão: oraculo)

EXEMPLO DE .env:
  EASYPANEL_URL=https://seu-easypanel.host
  EASYPANEL_TOKEN=seu-token-gerado
  EASYPANEL_PROJECT_NAME=oraculo
  NVIDIA_API_KEY=sua-chave
  OPENAI_API_KEY=sua-chave

O SCRIPT IRÁ:
  1. Validar que .env existe
  2. Carregar variáveis de ambiente
  3. Executar npx tsx scripts/easypanel-provision.ts
  4. Salvar output em .easypanel-provision-output.json

EOF
}

# ============================================================================
# MAIN
# ============================================================================

# Parse arguments
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --help|-h)
      show_help
      exit 0
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    *)
      err "Unknown argument: $arg"
      echo ""
      show_help
      exit 1
      ;;
  esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"

log "Easypanel Provisioning Wrapper"
log ""

# ============================================================================
# 1. VALIDAR .env
# ============================================================================

log "Checking for .env file..."
if [[ ! -f "$ENV_FILE" ]]; then
  err ".env file not found at $ENV_FILE"
  echo ""
  err "Please create a .env file with the following variables:"
  echo "  EASYPANEL_URL=https://your-easypanel.host"
  echo "  EASYPANEL_TOKEN=your-token"
  echo "  EASYPANEL_PROJECT_NAME=oraculo"
  echo ""
  err "You can copy from .env.easypanel.example:"
  echo "  cp .env.easypanel.example .env"
  echo "  nano .env"
  exit 1
fi

ok ".env file found"

# ============================================================================
# 2. CARREGAR VARIÁVEIS
# ============================================================================

log "Loading environment variables from .env..."

# Carregar .env no shell atual
set -a
# shellcheck source=.env
source "$ENV_FILE"
set +a

ok "Environment variables loaded"

# ============================================================================
# 3. VALIDAR VARIÁVEIS OBRIGATÓRIAS
# ============================================================================

log "Validating required variables..."

if [[ -z "${EASYPANEL_URL:-}" ]]; then
  err "EASYPANEL_URL not set in .env"
  exit 1
fi

if [[ -z "${EASYPANEL_TOKEN:-}" ]]; then
  err "EASYPANEL_TOKEN not set in .env"
  exit 1
fi

ok "EASYPANEL_URL: ${EASYPANEL_URL}"
ok "EASYPANEL_TOKEN: $(echo "${EASYPANEL_TOKEN:0:4}...${EASYPANEL_TOKEN: -4}")"
ok "EASYPANEL_PROJECT_NAME: ${EASYPANEL_PROJECT_NAME:-oraculo}"

# ============================================================================
# 4. DRY-RUN CHECK
# ============================================================================

if [[ $DRY_RUN -eq 1 ]]; then
  log ""
  warn "DRY-RUN MODE: Script will not actually provision anything"
  warn "To proceed with actual provisioning, run without --dry-run"
  log ""
  ok "All validations passed! Ready to provision."
  exit 0
fi

# ============================================================================
# 5. EXECUTAR PROVISIONING
# ============================================================================

log ""
log "========================================================================="
log "Starting Easypanel provisioning..."
log "========================================================================="
log ""

cd "$PROJECT_ROOT"

# Executar o script de provisioning
# Variables estão no ambiente agora, então npm run vai funcionar
npx tsx scripts/easypanel-provision.ts

log ""
ok "========================================================================="
ok "Provisioning Complete!"
ok "========================================================================="
log ""

# Verificar se output foi gerado
if [[ -f "$PROJECT_ROOT/.easypanel-provision-output.json" ]]; then
  ok "Output saved to: .easypanel-provision-output.json"
  log ""
  log "Next steps:"
  log "  1. Copy credentials to .env (if not auto-filled)"
  log "  2. Run: docker-compose -f docker-compose.easypanel.yml up -d"
  log "  3. Monitor logs: docker-compose logs -f"
else
  warn "Output file not found (may have failed)"
  exit 1
fi
