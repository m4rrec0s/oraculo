"""Enterprise Permission Manager — perfis e controle de acesso."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class ProfileType(str, Enum):
    """Tipos de perfil disponíveis."""
    ADMIN = "admin"
    ATENDIMENTO = "atendimento"


@dataclass
class ToolPermission:
    """Permissão para uma tool específica."""
    name: str
    allowed: bool = True
    rate_limit: int | None = None  # calls/min
    categories: list[str] = field(default_factory=list)


@dataclass
class SkillPermission:
    """Permissão para uma skill específica."""
    name: str
    allowed: bool = True
    max_per_turn: int = 3


@dataclass
class MCPPermission:
    """Permissão para um servidor MCP."""
    name: str
    allowed: bool = True
    tools: list[str] = field(default_factory=list)  # tools específicas permitidas


@dataclass
class Profile:
    """Definição completa de um perfil."""
    name: ProfileType
    display_name: str
    description: str
    tools: list[ToolPermission] = field(default_factory=list)
    skills: list[SkillPermission] = field(default_factory=list)
    mcps: list[MCPPermission] = field(default_factory=list)
    admin_operations: list[str] = field(default_factory=list)
    gateway_platforms: list[str] = field(default_factory=list)
    personalities: list[str] = field(default_factory=list)
    max_iterations: int = 8
    max_skills_per_turn: int = 3
    context_compression_threshold: float = 0.5
    can_manage_profiles: bool = False
    can_manage_skills: bool = False
    can_manage_mcps: bool = False
    can_view_analytics: bool = False
    can_access_crm: bool = False
    can_manage_gateway: bool = False

    def get_allowed_tools(self) -> list[str]:
        """Retorna lista de tools permitidas."""
        return [t.name for t in self.tools if t.allowed]

    def get_allowed_skills(self) -> list[str]:
        """Retorna lista de skills permitidas."""
        return [s.name for s in self.skills if s.allowed]

    def get_allowed_mcps(self) -> list[str]:
        """Retorna lista de MCPs permitidos."""
        return [m.name for m in self.mcps if m.allowed]

    def to_dict(self) -> dict[str, Any]:
        """Serializa para dict."""
        return {
            "name": self.name.value,
            "display_name": self.display_name,
            "description": self.description,
            "tools": [
                {"name": t.name, "allowed": t.allowed, "rate_limit": t.rate_limit, "categories": t.categories}
                for t in self.tools
            ],
            "skills": [
                {"name": s.name, "allowed": s.allowed, "max_per_turn": s.max_per_turn}
                for s in self.skills
            ],
            "mcps": [
                {"name": m.name, "allowed": m.allowed, "tools": m.tools}
                for m in self.mcps
            ],
            "admin_operations": self.admin_operations,
            "gateway_platforms": self.gateway_platforms,
            "personalities": self.personalities,
            "max_iterations": self.max_iterations,
            "max_skills_per_turn": self.max_skills_per_turn,
            "context_compression_threshold": self.context_compression_threshold,
            "can_manage_profiles": self.can_manage_profiles,
            "can_manage_skills": self.can_manage_skills,
            "can_manage_mcps": self.can_manage_mcps,
            "can_view_analytics": self.can_view_analytics,
            "can_access_crm": self.can_access_crm,
            "can_manage_gateway": self.can_manage_gateway,
        }


class PermissionManager:
    """Gerencia perfis e permissões do Hermes Enterprise."""

    DEFAULT_PROFILES: dict[ProfileType, Profile] = {}

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or Path.home() / ".hermes" / "enterprise" / "permissions"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[ProfileType, Profile] = {}
        self._current_profile: ProfileType | None = None
        self._load_default_profiles()
        self._load_custom_profiles()

    def _load_default_profiles(self) -> None:
        """Carrega perfis padrão do sistema."""
        # Perfil ADMIN — acesso total
        admin = Profile(
            name=ProfileType.ADMIN,
            display_name="Administrador",
            description="Acesso total ao sistema, gestão de perfis, skills, MCPs, gateway e analytics",
            tools=[
                ToolPermission(name="*", allowed=True),  # todas as tools
            ],
            skills=[
                SkillPermission(name="*", allowed=True, max_per_turn=5),
            ],
            mcps=[
                MCPPermission(name="*", allowed=True),
            ],
            admin_operations=[
                "profile_create", "profile_update", "profile_delete", "profile_list",
                "skill_create", "skill_update", "skill_delete", "skill_install",
                "mcp_register", "mcp_update", "mcp_remove",
                "gateway_start", "gateway_stop", "gateway_restart", "gateway_status",
                "config_edit", "config_view", "backup_create", "backup_restore",
                "plugin_install", "plugin_update", "plugin_remove",
            ],
            gateway_platforms=[
                "telegram", "discord", "whatsapp", "slack", "signal", "email",
                "matrix", "mattermost", "homeassistant", "qqbot", "yuanbao",
            ],
            personalities=[
                "helpful", "concise", "technical", "creative", "teacher",
                "kawaii", "catgirl", "pirate", "shakespeare", "surfer",
                "noir", "uwu", "philosopher", "hype",
            ],
            max_iterations=15,
            max_skills_per_turn=5,
            context_compression_threshold=0.3,
            can_manage_profiles=True,
            can_manage_skills=True,
            can_manage_mcps=True,
            can_view_analytics=True,
            can_access_crm=True,
            can_manage_gateway=True,
        )

        # Perfil ATENDIMENTO — restrito para Ana/Cesto d'Amore
        atendimento = Profile(
            name=ProfileType.ATENDIMENTO,
            display_name="Atendimento Cesto d'Amore",
            description="Perfil restrito para agente de atendimento Ana — apenas tools/skills de atendimento ao cliente",
            tools=[
                ToolPermission(name="search_products", allowed=True, rate_limit=20, categories=["product_search"]),
                ToolPermission(name="get_product_details", allowed=True, rate_limit=30, categories=["product_search"]),
                ToolPermission(name="calculate_delivery", allowed=True, rate_limit=15, categories=["delivery"]),
                ToolPermission(name="check_delivery_zone", allowed=True, rate_limit=10, categories=["delivery"]),
                ToolPermission(name="create_order", allowed=True, rate_limit=5, categories=["checkout"]),
                ToolPermission(name="get_order_status", allowed=True, rate_limit=15, categories=["checkout"]),
                ToolPermission(name="apply_coupon", allowed=True, rate_limit=5, categories=["checkout"]),
                ToolPermission(name="get_customization_options", allowed=True, rate_limit=15, categories=["product_search"]),
                ToolPermission(name="validate_customization", allowed=True, rate_limit=10, categories=["product_search"]),
                ToolPermission(name="consultar_documentacao", allowed=True, rate_limit=30, categories=["general"]),
                ToolPermission(name="detect_purchase_intent", allowed=True, rate_limit=30, categories=["general"]),
                ToolPermission(name="resolve_purchase_url", allowed=True, rate_limit=30, categories=["general"]),
                ToolPermission(name="recall_customer", allowed=True, rate_limit=10, categories=["knowledge"]),
                ToolPermission(name="save_preference", allowed=True, rate_limit=10, categories=["knowledge"]),
                ToolPermission(name="web_search", allowed=False),
                ToolPermission(name="web_extract", allowed=False),
                ToolPermission(name="terminal", allowed=False),
                ToolPermission(name="execute_code", allowed=False),
                ToolPermission(name="read_file", allowed=False),
                ToolPermission(name="write_file", allowed=False),
                ToolPermission(name="patch", allowed=False),
                ToolPermission(name="search_files", allowed=False),
                ToolPermission(name="vision_analyze", allowed=False),
                ToolPermission(name="image_generate", allowed=False),
                ToolPermission(name="browser_navigate", allowed=False),
                ToolPermission(name="todo", allowed=False),
                ToolPermission(name="memory", allowed=True, rate_limit=20, categories=["knowledge"]),
                ToolPermission(name="session_search", allowed=False),
                ToolPermission(name="skills_list", allowed=True, categories=["system"]),
                ToolPermission(name="skill_view", allowed=True, categories=["system"]),
                ToolPermission(name="cronjob", allowed=False),
            ],
            skills=[
                SkillPermission(name="delivery-guide", allowed=True, max_per_turn=1),
                SkillPermission(name="humanizer", allowed=True, max_per_turn=1),
                SkillPermission(name="customization-guide", allowed=True, max_per_turn=1),
            ],
            mcps=[
                MCPPermission(name="cesto-damore-erp", allowed=True, tools=[
                    "search_products", "get_product", "create_order", "get_order",
                    "calculate_delivery", "check_zone", "apply_coupon",
                    "get_customization_options", "validate_customization"
                ]),
                MCPPermission(name="cesto-damore-whatsapp", allowed=True, tools=[
                    "send_message", "send_template", "get_media"
                ]),
            ],
            admin_operations=[],
            gateway_platforms=["whatsapp"],
            personalities=["ana-atendimento"],
            max_iterations=8,
            max_skills_per_turn=3,
            context_compression_threshold=0.5,
            can_manage_profiles=False,
            can_manage_skills=False,
            can_manage_mcps=False,
            can_view_analytics=False,
            can_access_crm=False,
            can_manage_gateway=False,
        )

        self.DEFAULT_PROFILES = {
            ProfileType.ADMIN: admin,
            ProfileType.ATENDIMENTO: atendimento,
        }

        # Carregar perfis padrão se não existirem arquivos customizados
        for ptype, profile in self.DEFAULT_PROFILES.items():
            if ptype not in self._profiles:
                self._profiles[ptype] = profile

    def _load_custom_profiles(self) -> None:
        """Carrega perfis customizados do disco."""
        for profile_file in self.config_dir.glob("profile_*.json"):
            try:
                with open(profile_file, encoding="utf-8") as f:
                    data = json.load(f)
                ptype = ProfileType(data["name"])
                profile = self._dict_to_profile(data)
                self._profiles[ptype] = profile
                logger.info("permissions.profile_loaded", profile=ptype.value)
            except Exception as e:
                logger.warning("permissions.profile_load_failed", file=str(profile_file), error=str(e))

    def _dict_to_profile(self, data: dict[str, Any]) -> Profile:
        """Converte dict para Profile."""
        return Profile(
            name=ProfileType(data["name"]),
            display_name=data["display_name"],
            description=data["description"],
            tools=[
                ToolPermission(**t) for t in data.get("tools", [])
            ],
            skills=[
                SkillPermission(**s) for s in data.get("skills", [])
            ],
            mcps=[
                MCPPermission(**m) for m in data.get("mcps", [])
            ],
            admin_operations=data.get("admin_operations", []),
            gateway_platforms=data.get("gateway_platforms", []),
            personalities=data.get("personalities", []),
            max_iterations=data.get("max_iterations", 8),
            max_skills_per_turn=data.get("max_skills_per_turn", 3),
            context_compression_threshold=data.get("context_compression_threshold", 0.5),
            can_manage_profiles=data.get("can_manage_profiles", False),
            can_manage_skills=data.get("can_manage_skills", False),
            can_manage_mcps=data.get("can_manage_mcps", False),
            can_view_analytics=data.get("can_view_analytics", False),
            can_access_crm=data.get("can_access_crm", False),
            can_manage_gateway=data.get("can_manage_gateway", False),
        )

    def get_profile(self, profile_type: ProfileType) -> Profile | None:
        """Obtém perfil por tipo."""
        return self._profiles.get(profile_type)

    def get_current_profile(self) -> Profile | None:
        """Obtém perfil atual ativo."""
        if self._current_profile:
            return self._profiles.get(self._current_profile)
        return None

    def set_current_profile(self, profile_type: ProfileType) -> bool:
        """Define perfil atual."""
        if profile_type in self._profiles:
            self._current_profile = profile_type
            logger.info("permissions.profile_activated", profile=profile_type.value)
            return True
        return False

    def list_profiles(self) -> list[Profile]:
        """Lista todos os perfis disponíveis."""
        return list(self._profiles.values())

    def save_profile(self, profile: Profile) -> bool:
        """Salva perfil customizado no disco."""
        try:
            filepath = self.config_dir / f"profile_{profile.name.value}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
            self._profiles[profile.name] = profile
            logger.info("permissions.profile_saved", profile=profile.name.value)
            return True
        except Exception as e:
            logger.error("permissions.profile_save_failed", profile=profile.name.value, error=str(e))
            return False

    def check_tool_permission(self, tool_name: str, profile_type: ProfileType | None = None) -> bool:
        """Verifica se uma tool é permitida para o perfil."""
        profile = self.get_profile(profile_type or self._current_profile or ProfileType.ADMIN)
        if not profile:
            return False

        # Wildcard para admin
        for tool in profile.tools:
            if tool.name == "*" and tool.allowed:
                return True
            if tool.name == tool_name:
                return tool.allowed
        return False

    def check_skill_permission(self, skill_name: str, profile_type: ProfileType | None = None) -> bool:
        """Verifica se uma skill é permitida para o perfil."""
        profile = self.get_profile(profile_type or self._current_profile or ProfileType.ADMIN)
        if not profile:
            return False

        for skill in profile.skills:
            if skill.name == "*" and skill.allowed:
                return True
            if skill.name == skill_name:
                return skill.allowed
        return False

    def check_mcp_permission(self, mcp_name: str, tool_name: str | None = None, profile_type: ProfileType | None = None) -> bool:
        """Verifica se um MCP (e tool específica) é permitido para o perfil."""
        profile = self.get_profile(profile_type or self._current_profile or ProfileType.ADMIN)
        if not profile:
            return False

        for mcp in profile.mcps:
            if mcp.name == "*" and mcp.allowed:
                return True
            if mcp.name == mcp_name and mcp.allowed:
                if tool_name is None:
                    return True
                if not mcp.tools or tool_name in mcp.tools:
                    return True
        return False

    def filter_tools_for_profile(self, all_tools: list[dict], profile_type: ProfileType | None = None) -> list[dict]:
        """Filtra lista de tools para as permitidas no perfil."""
        profile = self.get_profile(profile_type or self._current_profile or ProfileType.ADMIN)
        if not profile:
            return []

        allowed = profile.get_allowed_tools()
        if "*" in allowed:
            return all_tools

        return [t for t in all_tools if t.get("function", {}).get("name") in allowed]

    def filter_skills_for_profile(self, all_skills: list[dict], profile_type: ProfileType | None = None) -> list[dict]:
        """Filtra lista de skills para as permitidas no perfil."""
        profile = self.get_profile(profile_type or self._current_profile or ProfileType.ADMIN)
        if not profile:
            return []

        allowed = profile.get_allowed_skills()
        if "*" in allowed:
            return all_skills

        return [s for s in all_skills if s.get("name") in allowed]


# Singleton global
permission_manager = PermissionManager()