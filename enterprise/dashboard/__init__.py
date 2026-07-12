"""Enterprise Dashboard — Módulos CRM, Analytics, Learning, Admin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from enterprise.crm.client import CRMClient, Customer, Conversation
from enterprise.learning.engine import LearningEngine, LearningProposal, LearningStatus
from enterprise.permissions.manager import PermissionManager, ProfileType


# ==================== MODELS ====================

class CRMStats(BaseModel):
    total_customers: int
    active_conversations: int
    conversions_today: int
    avg_response_time_ms: float


class AnalyticsOverview(BaseModel):
    conversions: dict[str, Any]
    sentiment: dict[str, Any]
    top_products: list[dict]
    period_days: int


class LearningProposalResponse(BaseModel):
    id: str
    change_type: str
    target: str
    title: str
    description: str
    confidence: float
    status: str
    created_at: str


# ==================== ROUTERS ====================

crm_router = APIRouter(prefix="/api/enterprise/crm", tags=["CRM"])
analytics_router = APIRouter(prefix="/api/enterprise/analytics", tags=["Analytics"])
learning_router = APIRouter(prefix="/api/enterprise/learning", tags=["Learning"])
admin_router = APIRouter(prefix="/api/enterprise/admin", tags=["Admin"])


# Dependency injection
async def get_crm_client() -> CRMClient:
    # Em produção, usar config do enterprise.yaml
    client = CRMClient(
        base_url="https://api.cestodamore.com.br",
        api_key="env:CRM_API_KEY",  # será resolvido pelo config loader
    )
    try:
        yield client
    finally:
        await client.close()


async def get_learning_engine() -> LearningEngine:
    engine = LearningEngine()
    try:
        yield engine
    finally:
        pass


async def get_permission_manager() -> PermissionManager:
    return PermissionManager()


# ==================== CRM ENDPOINTS ====================

@crm_router.get("/stats", response_model=CRMStats)
async def get_crm_stats(crm: CRMClient = Depends(get_crm_client)) -> CRMStats:
    """Estatísticas gerais do CRM."""
    # Implementar queries reais
    return CRMStats(
        total_customers=0,
        active_conversations=0,
        conversions_today=0,
        avg_response_time_ms=0.0,
    )


@crm_router.get("/customers/{phone}")
async def get_customer(phone: str, crm: CRMClient = Depends(get_crm_client)) -> Customer:
    """Busca cliente por telefone."""
    customer = await crm.get_customer(phone)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@crm_router.post("/customers")
async def create_customer(customer: Customer, crm: CRMClient = Depends(get_crm_client)) -> Customer:
    """Cria novo cliente."""
    created = await crm.create_customer(customer)
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create customer")
    return created


@crm_router.put("/customers/{phone}")
async def update_customer(phone: str, customer: Customer, crm: CRMClient = Depends(get_crm_client)) -> Customer:
    """Atualiza cliente."""
    customer.phone = phone
    success = await crm.update_customer(customer)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update customer")
    return customer


@crm_router.get("/customers/{phone}/conversations")
async def get_customer_conversations(
    phone: str, limit: int = Query(50, le=200), crm: CRMClient = Depends(get_crm_client)
) -> list[Conversation]:
    """Histórico de conversas do cliente."""
    return await crm.get_customer_conversations(phone, limit)


@crm_router.post("/customers/{phone}/tags")
async def add_customer_tag(phone: str, tag: str, crm: CRMClient = Depends(get_crm_client)) -> dict:
    """Adiciona tag ao cliente."""
    success = await crm.add_tag(phone, tag)
    return {"success": success, "phone": phone, "tag": tag}


# ==================== ANALYTICS ENDPOINTS ====================

@analytics_router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    days: int = Query(30, ge=1, le=365),
    crm: CRMClient = Depends(get_crm_client),
) -> AnalyticsOverview:
    """Visão geral de analytics."""
    conversions = await crm.get_conversion_metrics(days)
    sentiment = await crm.get_sentiment_analysis(days)
    top_products = await crm.get_top_products(days, 10)
    
    return AnalyticsOverview(
        conversions=conversions,
        sentiment=sentiment,
        top_products=top_products,
        period_days=days,
    )


@analytics_router.get("/conversions")
async def get_conversions(days: int = Query(30, ge=1, le=365), crm: CRMClient = Depends(get_crm_client)) -> dict:
    """Métricas de conversão detalhadas."""
    return await crm.get_conversion_metrics(days)


@analytics_router.get("/sentiment")
async def get_sentiment(days: int = Query(30, ge=1, le=365), crm: CRMClient = Depends(get_crm_client)) -> dict:
    """Análise de sentimento."""
    return await crm.get_sentiment_analysis(days)


@analytics_router.get("/top-products")
async def get_top_products(days: int = Query(30, ge=1, le=365), limit: int = Query(10, le=50), crm: CRMClient = Depends(get_crm_client)) -> list:
    """Produtos mais vendidos/mencionados."""
    return await crm.get_top_products(days, limit)


# ==================== LEARNING ENDPOINTS ====================

@learning_router.get("/proposals", response_model=list[LearningProposalResponse])
async def list_proposals(
    status: LearningStatus | None = None,
    engine: LearningEngine = Depends(get_learning_engine),
) -> list[LearningProposalResponse]:
    """Lista propostas de aprendizado."""
    proposals = engine.get_proposals(status)
    return [LearningProposalResponse(**p.to_dict()) for p in proposals]


@learning_router.get("/proposals/{proposal_id}", response_model=LearningProposalResponse)
async def get_proposal(proposal_id: str, engine: LearningEngine = Depends(get_learning_engine)) -> LearningProposalResponse:
    """Detalhes de uma proposta."""
    proposals = engine.get_proposals()
    proposal = next((p for p in proposals if p.id == proposal_id), None)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return LearningProposalResponse(**proposal.to_dict())


@learning_router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, approved_by: str, engine: LearningEngine = Depends(get_learning_engine)) -> dict:
    """Aprova proposta para deploy."""
    success = engine.approve_proposal(proposal_id, approved_by)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot approve proposal")
    return {"success": True, "proposal_id": proposal_id}


@learning_router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, reason: str, engine: LearningEngine = Depends(get_learning_engine)) -> dict:
    """Rejeita proposta."""
    success = engine.reject_proposal(proposal_id, reason)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot reject proposal")
    return {"success": True, "proposal_id": proposal_id}


@learning_router.post("/proposals/{proposal_id}/deploy")
async def deploy_proposal(proposal_id: str, engine: LearningEngine = Depends(get_learning_engine)) -> dict:
    """Deploya proposta aprovada."""
    success = engine.deploy_proposal(proposal_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot deploy proposal")
    return {"success": True, "proposal_id": proposal_id}


@learning_router.post("/proposals/{proposal_id}/rollback")
async def rollback_proposal(proposal_id: str, engine: LearningEngine = Depends(get_learning_engine)) -> dict:
    """Rollback de proposta deployada."""
    success = engine.rollback_proposal(proposal_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot rollback proposal")
    return {"success": True, "proposal_id": proposal_id}


@learning_router.post("/analyze")
async def trigger_analysis(days_back: int = 7, engine: LearningEngine = Depends(get_learning_engine)) -> dict:
    """Dispara análise manual de sessões."""
    proposals = await engine.analyze_sessions(days_back)
    return {"analyzed": True, "proposals_generated": len(proposals)}


# ==================== ADMIN ENDPOINTS ====================

@admin_router.get("/profiles")
async def list_profiles(pm: PermissionManager = Depends(get_permission_manager)) -> list[dict]:
    """Lista perfis disponíveis."""
    return [p.to_dict() for p in pm.list_profiles()]


@admin_router.get("/profiles/{profile_type}")
async def get_profile(profile_type: ProfileType, pm: PermissionManager = Depends(get_permission_manager)) -> dict:
    """Detalhes de um perfil."""
    profile = pm.get_profile(profile_type)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile.to_dict()


@admin_router.post("/profiles/{profile_type}/activate")
async def activate_profile(profile_type: ProfileType, pm: PermissionManager = Depends(get_permission_manager)) -> dict:
    """Ativa perfil."""
    success = pm.set_current_profile(profile_type)
    return {"success": success, "active_profile": profile_type.value}


@admin_router.get("/permissions/check/tool")
async def check_tool_permission(tool: str, profile: ProfileType | None = None, pm: PermissionManager = Depends(get_permission_manager)) -> dict:
    """Verifica permissão de tool."""
    allowed = pm.check_tool_permission(tool, profile)
    return {"tool": tool, "allowed": allowed, "profile": (profile or pm._current_profile).value}


@admin_router.get("/permissions/check/skill")
async def check_skill_permission(skill: str, profile: ProfileType | None = None, pm: PermissionManager = Depends(get_permission_manager)) -> dict:
    """Verifica permissão de skill."""
    allowed = pm.check_skill_permission(skill, profile)
    return {"skill": skill, "allowed": allowed, "profile": (profile or pm._current_profile).value}


@admin_router.get("/health")
async def enterprise_health() -> dict:
    """Health check enterprise."""
    return {
        "enterprise": "healthy",
        "modules": {
            "crm": "ok",
            "analytics": "ok",
            "learning": "ok",
            "permissions": "ok",
            "mcp": "ok",
        },
    }


# ==================== AGGREGATE ROUTER ====================

enterprise_router = APIRouter(prefix="/api/enterprise")
enterprise_router.include_router(crm_router)
enterprise_router.include_router(analytics_router)
enterprise_router.include_router(learning_router)
enterprise_router.include_router(admin_router)