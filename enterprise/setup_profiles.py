#!/usr/bin/env python3
"""Enterprise — Setup de Profiles.

Cria e configura os profiles isolados para Ana e Admin.
"""

import os
import shutil
from pathlib import Path

from hermes_constants import get_hermes_home


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# Profiles
PROFILES = {
    "admin": {
        "name": "admin",
        "description": "Hermes Admin — controle total do sistema",
        "home": Path("~/.hermes").expanduser(),
    },
    "ana": {
        "name": "ana",
        "description": "Ana — atendimento ao cliente",
        "home": Path("~/.hermes/profiles/ana").expanduser(),
    },
}

# Diretórios padrão em cada profile
PROFILE_DIRS = [
    "memories",
    "sessions",
    "skills",
    "skins",
    "logs",
    "plans",
    "workspace",
    "cron",
    "home",
]


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def create_profile(profile_name: str, clone_from: str = None) -> Path:
    """Cria um profile com a estrutura padrão.
    
    Args:
        profile_name: Nome do profile (admin ou ana)
        clone_from: Profile base para clone (opcional)
        
    Returns:
        Path do profile criado
    """
    config = PROFILES.get(profile_name)
    if not config:
        raise ValueError(f"Profile desconhecido: {profile_name}")
    
    profile_home = config["home"]
    
    # Criar diretório principal
    profile_home.mkdir(parents=True, exist_ok=True)
    
    # Criar subdiretórios
    for subdir in PROFILE_DIRS:
        (profile_home / subdir).mkdir(parents=True, exist_ok=True)
    
    # Clonar de outro profile se especificado
    if clone_from and clone_from in PROFILES:
        source_home = PROFILES[clone_from]["home"]
        if source_home.exists():
            # Copiar config.yaml e .env
            for config_file in ["config.yaml", ".env"]:
                source_file = source_home / config_file
                if source_file.exists():
                    dest_file = profile_home / config_file
                    if not dest_file.exists():
                        shutil.copy2(source_file, dest_file)
    
    print(f"Profile criado: {profile_home}")
    return profile_home


def setup_ana_profile() -> Path:
    """Configura o profile da Ana com settings específicas."""
    profile_home = create_profile("ana", clone_from="admin")
    
    # Criar config.yaml da Ana (se não existir)
    config_file = profile_home / "config.yaml"
    if not config_file.exists():
        config_content = """# Ana — Configuração de Atendimento
# Profile isolado para atendimento ao cliente

# Modelo (usar modelo leve/custo-baixo)
model:
  provider: openai
  name: gpt-4o-mini

# Agent
agent:
  max_iterations: 5
  skip_memory: false

# Skills (apenas atendimento)
skills:
  enabled:
    - ana-atendimento
    - cesto-damore
  disabled:
    - hermes-agent
    - github-repo-management

# Tools (restrições de segurança)
tools:
  enabled:
    - send_message
    - send_template
    - get_media
    - search_products
    - get_product
    - calculate_delivery
    - check_zone
    - get_customization_options
    - memory
    - session_search
  disabled:
    - terminal
    - execute_code
    - read_file
    - write_file
    - patch
    - search_files
    - skill_manage
    - skills_list
    - config_manage

# Memória (por sessão/cliente)
memory:
  provider: builtin
  session_scoped: true

# Logging
logging:
  level: INFO
"""
        config_file.write_text(config_content)
        print(f"Config.yaml da Ana criado: {config_file}")
    
    # Criar .env da Ana (se não existir)
    env_file = profile_home / ".env"
    if not env_file.exists():
        env_content = """# Ana — Variáveis de Ambiente
# ATENÇÃO: Não commite este arquivo!

# API Keys (usar as mesmas do admin)
OPENAI_API_KEY=sk-proj-xxx

# WhatsApp (para envio de mensagens)
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=

# Database (mesmo Postgres do ERP)
CESTO_PG_HOST=easypanel.cestodamore.com.br
CESTO_PG_PORT=54320
CESTO_PG_DATABASE=cesto_damore
CESTO_PG_USER=postgres
CESTO_PG_PASSWORD=
"""
        env_file.write_text(env_content)
        print(f".env da Ana criado: {env_file}")
    
    # Criar skill da Ana (se não existir)
    skills_dir = profile_home / "skills" / "cesto-damore"
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    skill_file = skills_dir / "ana-atendimento.md"
    if not skill_file.exists():
        skill_content = """# Ana Atendimento — Cesto d'Amore

Você é **Ana**, atendente da Cesto d'Amore.

## Identidade
- **Nome:** Ana
- **Empresa:** Cesto d'Amore
- **Tom:** Informal, calorosa
- **Idioma:** Português brasileiro

## Regras
1. Toda intenção de compra → site
2. Nunca inventar composições
3. Nunca passar preços sem o site
4. Redirecionar para https://www.cestodamore.com.br

## Horários
- Seg a Sex: 08:30–12:00 | 14:00–17:00
- Sábado: 08:00–11:00
- Domingo: Fechado

## Entrega
- Campina Grande: grátis via PIX
- Entrega própria: R$ 15 (2-4h)
"""
        skill_file.write_text(skill_content)
        print(f"Skill da Ana criada: {skill_file}")
    
    return profile_home


def setup_admin_profile() -> Path:
    """Configura o profile do Admin."""
    profile_home = create_profile("admin")
    
    # Admin usa a configuração padrão do Hermes
    # Apenas garantir que os diretórios existem
    print(f"Profile do Admin configurado: {profile_home}")
    
    return profile_home


def setup_all_profiles():
    """Configura todos os profiles."""
    print("=" * 60)
    print("Enterprise — Setup de Profiles")
    print("=" * 60)
    
    # 1. Setup Admin
    print("\n1. Configurando profile Admin...")
    setup_admin_profile()
    
    # 2. Setup Ana
    print("\n2. Configurando profile Ana...")
    setup_ana_profile()
    
    print("\n" + "=" * 60)
    print("Setup concluído!")
    print("=" * 60)
    print("\nPróximos passos:")
    print("1. Configurar API keys em ~/.hermes/.env (admin)")
    print("2. Configurar API keys em ~/.hermes/profiles/ana/.env (ana)")
    print("3. Configurar PostgreSQL (enterprise/mcp/ana_sessions.py)")
    print("4. Executar: docker-compose -f docker-compose.enterprise.yml up")
    print("\nHeaders para routing:")
    print("  X-Hermes-Agent: admin  → Controle total")
    print("  X-Hermes-Agent: ana    → Atendimento restrito")
    print("  (header ausente)       → Ana (fail-safe)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "admin":
            setup_admin_profile()
        elif command == "ana":
            setup_ana_profile()
        elif command == "all":
            setup_all_profiles()
        else:
            print(f"Comando desconhecido: {command}")
            print("Uso: python setup_profiles.py [admin|ana|all]")
    else:
        setup_all_profiles()
