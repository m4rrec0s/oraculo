"""Enterprise Profiles — gerenciamento de perfis de operação do Hermes."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProfileType(str, Enum):
    """Tipos de perfil suportados."""
    ADMIN = "admin"
    ATENDIMENTO = "atendimento"


class ToolPermission(BaseModel):
    """Permissão para uma tool específica."""
    name: str
    allowed: bool = True
    rate_limit: int | None = None
    categories: list[str] = Field(default_factory=list)


class SkillPermission(BaseModel):
    """Permissão para uma skill específica."""
    name: str
    allowed: bool = True
    max_per_turn: int = 3
    required_categories: list[str] = Field(default_factory=list)


class MCPPermission(BaseModel):
    """Permissão para um servidor MCP."""
    name: str
    allowed: bool = True
    tools: list[str] = Field(default_factory=list)


class Profile(BaseModel):
    """Definição completa de um perfil de operação."""
    name: ProfileType
    display_name: str
    description: str
    tools: list[ToolPermission] = Field(default_factory=list)
    skills: list[SkillPermission] = Field(default_factory=list)
    mcps: list[MCPPermission] = Field(default_factory=list)
    admin_operations: list[str] = Field(default_factory=list)
    gateway_platforms: list[str] = Field(default_factory=list)
    personalities: list[str] = Field(default_factory=list)
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
        """Converte para dict para serialização."""
        return {
            "name": self.name.value,
            "display_name": self.display_name,
            "description": self.description,
            "tools": [t.model_dump() for t in self.tools],
            "skills": [s.model_dump() for s in self.skills],
            "mcps": [m.model_dump() for m in self.mcps],
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        """Cria Profile a partir de dict."""
        return cls(
            name=ProfileType(data["name"]),
            display_name=data["display_name"],
            description=data["description"],
            tools=[ToolPermission(**t) for t in data.get("tools", [])],
            skills=[SkillPermission(**s) for s in data.get("skills", [])],
            mcps=[MCPPermission(**m) for m in data.get("mcps", [])],
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