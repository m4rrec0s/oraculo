#!/bin/bash
# Wrapper para scripts/seed-sync.py
# Chama o script Python de seed granular com os argumentos corretos

set -euo pipefail

# Diretório raiz do projeto (onde está o Dockerfile)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Localização do script Python
SEED_SYNC_PYTHON="${SCRIPT_DIR}/seed-sync.py"

# Verifica se Python está disponível
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 não encontrado no PATH" >&2
    exit 1
fi

# Verifica se o script Python existe
if [[ ! -f "$SEED_SYNC_PYTHON" ]]; then
    echo "[ERROR] script seed-sync.py não encontrado: $SEED_SYNC_PYTHON" >&2
    exit 1
fi

# Argumentos passados para o script Python:
# 1. template_dir - diretório com o template de skills/persona
# 2. profile_home - diretório do profile no volume persistente
# 3. profile - nome do profile (admin/atendimento)
TEMPLATE_DIR="${1:-/home/hermes/enterprise}"
PROFILE_HOME="${2:-/home/hermes/.hermes/profiles/atendimento}"
PROFILE="${3:-atendimento}"

# Executa o script Python
exec python3 "$SEED_SYNC_PYTHON" "$TEMPLATE_DIR" "$PROFILE_HOME" "$PROFILE"
