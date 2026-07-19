"""Enterprise Config Settings — Pydantic settings para configuração enterprise."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnterpriseConfig(BaseSettings):
    """Configuração completa do Hermes Enterprise."""

    model_config = SettingsConfigDict(
        env_file=".env.enterprise",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Enterprise
    enterprise_enabled: bool = True
    company_name: str = "Cesto d'Amore"
    domain: str = "cestodamore.com.br"
    environment: str = "production"

    # Profiles
    default_profile: str = "atendimento"
    auto_switch_by_gateway: bool = True

    # Permissions
    permissions_dir: str = "~/.hermes/enterprise/permissions"
    enforce_at_registry: bool = True

    # CRM
    crm_enabled: bool = True
    crm_backend_url: str = "https://api.cestodamore.com.br"
    crm_api_key: str | None = None
    crm_sync_interval_minutes: int = 15
    crm_conversation_retention_days: int = 365

    # Analytics
    analytics_enabled: bool = True
    analytics_export_interval_hours: int = 1
    analytics_retention_days: int = 730

    # Learning
    learning_enabled: bool = True
    learning_admin_only: bool = True
    learning_analyzer_model: str = "gpt-4o"
    learning_min_sessions: int = 50
    learning_max_daily_updates: int = 3
    learning_auto_deploy: bool = False
    learning_rollback_enabled: bool = True
    learning_version_history_limit: int = 50
    learning_audit_log: bool = True

    # Dashboard
    dashboard_modules_crm: bool = True
    dashboard_modules_analytics: bool = True
    dashboard_modules_learning: bool = True
    dashboard_modules_administration: bool = True
    dashboard_theme: str = "cesto-damore"
    dashboard_brand_color: str = "#FF6B9D"
    dashboard_language: str = "pt-BR"

    # Integrations
    erp_mcp_server: str = "cesto-damore-erp"
    whatsapp_mcp_server: str = "cesto-damore-whatsapp"
    n8n_enabled: bool = True
    n8n_webhook_url: str = "https://n8n.cestodamore.com.br/webhook/hermes"
    n8n_events: list[str] = Field(default_factory=lambda: [
        "new_conversation", "order_created", "delivery_status", "customer_tag_added"
    ])

    # Gateway WhatsApp
    whatsapp_platform: str = "360dialog"
    whatsapp_phone_number_id: str = ""
    whatsapp_webhook_verify_token: str = ""
    whatsapp_rate_limit_per_phone: int = 10
    whatsapp_rate_limit_window_seconds: int = 60
    whatsapp_message_limit_chars: int = 300
    whatsapp_auto_split_long: bool = True
    whatsapp_media_support: bool = True

    # MCP Servers
    mcp_servers: dict[str, dict[str, Any]] = Field(default_factory=lambda: {
        "cesto-damore-erp": {
            "command": "npx",
            "args": ["-y", "@cestodamore/mcp-erp"],
            "env": {
                "ERP_API_URL": "https://api.cestodamore.com.br",
                "ERP_API_KEY": "",
            },
            "tools": [
                "search_products", "get_product", "create_order", "get_order",
                "calculate_delivery", "check_delivery_zone", "apply_coupon",
                "get_customization_options", "validate_customization"
            ],
            "profile_permissions": {
                "admin": ["*"],
                "atendimento": ["search_products", "get_product", "get_order", "calculate_delivery", "check_delivery_zone"]
            }
        },
        "cesto-damore-whatsapp": {
            "command": "npx",
            "args": ["-y", "@cestodamore/mcp-whatsapp"],
            "env": {
                "WHATSAPP_TOKEN": "",
                "WHATSAPP_PHONE_ID": "",
            },
            "tools": ["send_message", "send_template", "get_media"],
            "profile_permissions": {
                "admin": ["*"],
                "atendimento": ["send_message", "send_template"]
            }
        }
    })

    # Skills
    skills_enterprise_dir: str = "skills/cesto-damore"
    skills_auto_load: list[str] = Field(default_factory=lambda: [
        "humanizer", "entrega", "personalizacao", "politicas"
    ])
    skills_max_per_turn: int = 3

    # Models
    model_admin_default: str = "nvidia/nemotron-3-super-120b-a12b"
    model_admin_provider: str = "nvidia"
    model_admin_base_url: str = "https://integrate.api.nvidia.com/v1"
    model_atendimento_default: str = "gpt-4o-mini"
    model_atendimento_provider: str = "openai"
    model_atendimento_classifier: str = "gpt-4o-mini"
    model_atendimento_compression: str = "gpt-4o"
    model_atendimento_embeddings: str = "text-embedding-3-small"

    # Context Compression
    compression_enabled: bool = True
    compression_threshold_admin: float = 0.3
    compression_threshold_atendimento: float = 0.5
    compression_target_ratio: float = 0.2
    compression_protect_last_n_admin: int = 20
    compression_protect_last_n_atendimento: int = 15

    # Memory
    memory_enabled: bool = True
    memory_provider: str = "hybrid"
    memory_short_term_turns: int = 10
    memory_long_term_backend: str = "crm"
    memory_user_profile_enabled: bool = True
    memory_write_approval: bool = False

    # Logging & Security
    logging_level: str = "INFO"
    enterprise_logs: bool = True
    audit_trail: bool = True
    pii_redaction: bool = True
    tirith_enabled: bool = True
    website_blocklist_enabled: bool = True
    website_allowed_domains: list[str] = Field(default_factory=lambda: [
        "cestodamore.com.br", "cestodamore.com"
    ])
    secret_redaction: bool = True

    @field_validator("permissions_dir", "skills_enterprise_dir", mode="before")
    @classmethod
    def expand_path(cls, v: str) -> str:
        return str(Path(v).expanduser())

    def validate(self) -> list[str]:
        """Valida configuração e retorna lista de erros."""
        errors = []
        
        if self.environment == "production":
            if not self.crm_api_key:
                errors.append("CRM_API_KEY é obrigatório em produção")
            if not self.whatsapp_webhook_verify_token:
                errors.append("WHATSAPP_WEBHOOK_VERIFY_TOKEN é obrigatório em produção")
            if not self.mcp_servers.get("cesto-damore-erp", {}).get("env", {}).get("ERP_API_KEY"):
                errors.append("ERP_API_KEY é obrigatório em produção")
            if not self.mcp_servers.get("cesto-damore-whatsapp", {}).get("env", {}).get("WHATSAPP_TOKEN"):
                errors.append("WHATSAPP_TOKEN é obrigatório em produção")
        
        if self.learning_enabled and self.learning_auto_deploy and not self.learning_admin_only:
            errors.append("Auto-deploy requer learning_admin_only=true")
        
        return errors

    @classmethod
    def load(cls) -> "EnterpriseConfig":
        """Carrega configuração (singleton pattern)."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance

    def get_profile_model(self, profile: str) -> dict[str, str]:
        """Retorna config de modelo para um perfil.

        admin → config completa; qualquer outra persona → config minimal
        (padrão de atendimento). Perfis extras herdam o minimal.
        """
        if profile == "admin":
            return {
                "default": self.model_admin_default,
                "provider": self.model_admin_provider,
                "base_url": self.model_admin_base_url,
            }
        return {
            "default": self.model_atendimento_default,
            "provider": self.model_atendimento_provider,
            "classifier": self.model_atendimento_classifier,
            "compression": self.model_atendimento_compression,
            "embeddings": self.model_atendimento_embeddings,
        }

    def get_compression_config(self, profile: str) -> dict[str, Any]:
        """Retorna config de compressão para um perfil.

        admin → threshold admin; qualquer outra persona → threshold minimal.
        """
        if profile == "admin":
            return {
                "enabled": self.compression_enabled,
                "threshold": self.compression_threshold_admin,
                "target_ratio": self.compression_target_ratio,
                "protect_last_n": self.compression_protect_last_n_admin,
            }
        return {
            "enabled": self.compression_enabled,
            "threshold": self.compression_threshold_atendimento,
            "target_ratio": self.compression_target_ratio,
            "protect_last_n": self.compression_protect_last_n_atendimento,
        }


# Singleton
_enterprise_config: EnterpriseConfig | None = None


def get_enterprise_config() -> EnterpriseConfig:
    """Obtém instância singleton da configuração enterprise."""
    global _enterprise_config
    if _enterprise_config is None:
        _enterprise_config = EnterpriseConfig.load()
    return _enterprise_config