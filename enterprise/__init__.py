"""Hermes Enterprise — extensões corporativas para Cesto d'Amore.

Estrutura:
- crm: Gestão de clientes, conversas, produtos
- analytics: Métricas de conversão, sentimento, produtos
- permissions: Sistema de perfis e controle de acesso
- learning: Autoaprendizado via análise de sessões
- dashboard: Módulos do dashboard enterprise
- integrations: MCPs corporativos (ERP, WhatsApp, etc.)
- mcp: Framework para MCPs empresariais
- config: Configurações enterprise
- cli: Comandos CLI enterprise
"""

__version__ = "1.0.0"

# Lazy imports — only available when full enterprise deps are installed
# (structlog, pydantic_settings, etc.). Core modules like pg_session_store
# must NOT trigger these imports.
try:
    from enterprise.permissions.manager import PermissionManager, Profile
    from enterprise.config.settings import EnterpriseConfig
    __all__ = ["PermissionManager", "Profile", "EnterpriseConfig"]
except ImportError:
    __all__ = []
