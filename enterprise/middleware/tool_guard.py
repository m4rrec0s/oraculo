"""Enterprise — Tool Guard para Ana.

Restringe quais tools e skills a Ana pode usar.
Garante isolamento de segurança: Ana não pode se auto-modificar.
"""

from __future__ import annotations

from typing import Set

# ---------------------------------------------------------------------------
# Tools permitidas para a Ana
# ---------------------------------------------------------------------------

# Tools de comunicação (permitidas)
ANA_ALLOWED_TOOLS = {
    # WhatsApp
    "send_message",
    "send_template",
    "get_media",
    
    # ERP (leitura)
    "search_products",
    "get_product",
    "calculate_delivery",
    "check_zone",
    "get_customization_options",
    
    # Memória (leitura/escrita básica)
    "memory",
    
    # Sessão
    "session_search",
}

# Tools de administração (BLOQUEADAS para Ana)
ANA_BLOCKED_TOOLS = {
    # Administração
    "skill_manage",
    "skills_list",
    "skill_view",
    "config_manage",
    "profile_manage",
    
    # Terminal/Shell
    "terminal",
    "execute_code",
    "run_command",
    
    # Arquivos
    "read_file",
    "write_file",
    "patch",
    "search_files",
    
    # Git
    "git_status",
    "git_commit",
    "git_push",
    
    # Outros agentes
    "delegate_task",
    "spawn_subagent",
    
    # Auto-modificação
    "self_modify",
    "update_config",
    "install_skill",
    "uninstall_skill",
}

# Skills permitidas para a Ana
ANA_ALLOWED_SKILLS = {
    "ana-atendimento",
    "cesto-damore",
}

# Skills bloqueadas para a Ana
ANA_BLOCKED_SKILLS = {
    "hermes-agent",
    "github-repo-management",
    "shell-alias-management",
    "linux-desktop-autostart-management",
    "data-science",
    "software-development",
}


# ---------------------------------------------------------------------------
# Funções de validação
# ---------------------------------------------------------------------------

def is_tool_allowed(tool_name: str, agent: str = "ana") -> bool:
    """Verifica se uma tool está permitida para o agente.
    
    Args:
        tool_name: Nome da tool
        agent: Nome do agente (default: ana)
        
    Returns:
        True se permitida, False caso contrário
    """
    if agent == "admin":
        return True  # Admin tem acesso a tudo
    
    if agent == "ana":
        # Bloqueadas explicitamente
        if tool_name in ANA_BLOCKED_TOOLS:
            return False
        
        # Permitidas explicitamente
        if tool_name in ANA_ALLOWED_TOOLS:
            return True
        
        # Por padrão, bloquear (fail-safe restritivo)
        return False
    
    return False


def is_skill_allowed(skill_name: str, agent: str = "ana") -> bool:
    """Verifica se uma skill está permitida para o agente.
    
    Args:
        skill_name: Nome da skill
        agent: Nome do agente (default: ana)
        
    Returns:
        True se permitida, False caso contrário
    """
    if agent == "admin":
        return True  # Admin tem acesso a tudo
    
    if agent == "ana":
        # Bloqueadas explicitamente
        if skill_name in ANA_BLOCKED_SKILLS:
            return False
        
        # Permitidas explicitamente
        if skill_name in ANA_ALLOWED_SKILLS:
            return True
        
        # Verificar se começa com ana- ou cesto-damore
        if skill_name.startswith("ana-") or skill_name.startswith("cesto-damore"):
            return True
        
        # Por padrão, bloquear (fail-safe restritivo)
        return False
    
    return False


def get_allowed_tools(agent: str = "ana") -> Set[str]:
    """Retorna conjunto de tools permitidas para o agente.
    
    Args:
        agent: Nome do agente (default: ana)
        
    Returns:
        Conjunto de nomes de tools permitidas
    """
    if agent == "admin":
        return set()  # Vazio = todas permitidas
    
    return ANA_ALLOWED_TOOLS.copy()


def get_blocked_tools(agent: str = "ana") -> Set[str]:
    """Retorna conjunto de tools bloqueadas para o agente.
    
    Args:
        agent: Nome do agente (default: ana)
        
    Returns:
        Conjunto de nomes de tools bloqueadas
    """
    if agent == "admin":
        return set()  # Vazio = nenhuma bloqueada
    
    return ANA_BLOCKED_TOOLS.copy()


def get_allowed_skills(agent: str = "ana") -> Set[str]:
    """Retorna conjunto de skills permitidas para o agente.
    
    Args:
        agent: Nome do agente (default: ana)
        
    Returns:
        Conjunto de nomes de skills permitidas
    """
    if agent == "admin":
        return set()  # Vazio = todas permitidas
    
    return ANA_ALLOWED_SKILLS.copy()


def get_blocked_skills(agent: str = "ana") -> Set[str]:
    """Retorna conjunto de skills bloqueadas para o agente.
    
    Args:
        agent: Nome do agente (default: ana)
        
    Returns:
        Conjunto de nomes de skills bloqueadas
    """
    if agent == "admin":
        return set()  # Vazio = nenhuma bloqueada
    
    return ANA_BLOCKED_SKILLS.copy()


# ---------------------------------------------------------------------------
# Validação de segurança
# ---------------------------------------------------------------------------

def validate_tool_access(
    tool_name: str,
    agent: str,
    context: dict = None,
) -> bool:
    """Valida acesso completo de uma tool.
    
    Args:
        tool_name: Nome da tool
        agent: Agente solicitante
        context: Contexto adicional (cell, session_id, etc)
        
    Returns:
        True se acesso permitido
    """
    # Verificar se tool está na lista
    if not is_tool_allowed(tool_name, agent):
        return False
    
    # Validações adicionais por tool
    if tool_name in {"memory", "session_search"}:
        # Tools de memória só leem/escrevem dados do próprio agente
        if context and context.get("agent") != agent:
            return False
    
    return True


def validate_skill_access(
    skill_name: str,
    agent: str,
    context: dict = None,
) -> bool:
    """Valida acesso completo de uma skill.
    
    Args:
        skill_name: Nome da skill
        agent: Agente solicitante
        context: Contexto adicional
        
    Returns:
        True se acesso permitido
    """
    return is_skill_allowed(skill_name, agent)
