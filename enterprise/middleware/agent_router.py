"""Enterprise — Agent Router middleware.

Roteia requisições HTTP para o agente correto (admin ou ana) baseado no header
X-Hermes-Agent. Cada agente tem seu próprio HERMES_HOME, configuração, skills e tools.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

from hermes_constants import get_hermes_home


# ---------------------------------------------------------------------------
# Configuração de agentes
# ---------------------------------------------------------------------------

# Mapeamento de agentes para seus HERMES_HOME
AGENT_HOMES = {
    "admin": Path(os.getenv("HERMES_ADMIN_HOME", "~/.hermes")).expanduser(),
    "ana": Path(os.getenv("HERMES_ANA_HOME", "~/.hermes/profiles/ana")).expanduser(),
}

# Header name
AGENT_HEADER = "X-Hermes-Agent"

# Agente padrão quando header está ausente (fail-safe restritivo)
DEFAULT_AGENT = "ana"

# Agentes válidos
VALID_AGENTS = {"admin", "ana"}


# ---------------------------------------------------------------------------
# Resolução de agente
# ---------------------------------------------------------------------------

def resolve_agent(header_value: Optional[str]) -> Tuple[str, Path]:
    """Resolve qual agente processar a requisição.
    
    Args:
        header_value: Valor do header X-Hermes-Agent
        
    Returns:
        Tupla (agent_name, hermes_home)
        
    Security:
        - Header ausente ou inválido → Ana (fail-safe restritivo)
        - Header válido → agente correspondente
    """
    agent_name = (header_value or "").strip().lower()
    
    # Validar agente
    if agent_name not in VALID_AGENTS:
        agent_name = DEFAULT_AGENT
    
    # Resolver HERMES_HOME
    hermes_home = AGENT_HOMES.get(agent_name, AGENT_HOMES[DEFAULT_AGENT])
    
    return agent_name, hermes_home


def get_agent_from_request(request) -> Tuple[str, Path]:
    """Extrai agente de uma requisição HTTP.
    
    Args:
        request: Objeto request do aiohttp
        
    Returns:
        Tupla (agent_name, hermes_home)
    """
    header_value = request.headers.get(AGENT_HEADER)
    return resolve_agent(header_value)


def set_agent_home(agent_name: str) -> None:
    """Define HERMES_HOME para o agente especificado.
    
    ATENÇÃO: Isso muda o HERMES_HOME do processo!
    Só deve ser chamado no início do processamento de uma requisição.
    """
    hermes_home = AGENT_HOMES.get(agent_name)
    if hermes_home:
        os.environ["HERMES_HOME"] = str(hermes_home)


def restore_default_home() -> None:
    """Restaura HERMES_HOME para o valor padrão."""
    os.environ["HERMES_HOME"] = str(AGENT_HOMES[DEFAULT_AGENT])


# ---------------------------------------------------------------------------
# Validação de segurança
# ---------------------------------------------------------------------------

def validate_agent_access(
    agent_name: str,
    required_agent: str,
) -> bool:
    """Valida se o agente tem acesso a um recurso.
    
    Args:
        agent_name: Agente que está tentando acessar
        required_agent: Agente que tem acesso ao recurso
        
    Returns:
        True se acesso permitido, False caso contrário
    """
    return agent_name == required_agent


def is_admin_agent(agent_name: str) -> bool:
    """Verifica se é o agente admin."""
    return agent_name == "admin"


def is_ana_agent(agent_name: str) -> bool:
    """Verifica se é a Ana."""
    return agent_name == "ana"
