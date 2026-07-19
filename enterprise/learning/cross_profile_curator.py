"""Enterprise — Cross-Profile Learning.

Estende o curator para operar sobre perfis diferentes.
Permite que o Admin leia sessões da Ana e aplique melhorias.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# Profile da Ana (target de melhorias)
ANA_PROFILE = "ana"

# Profile do Admin (origem das melhorias)
ADMIN_PROFILE = "default"


# ---------------------------------------------------------------------------
# Leitura de sessões cross-profile
# ---------------------------------------------------------------------------

async def read_agent_sessions(
    agent_profile: str,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Lê sessões de outro agente (para análise).
    
    Args:
        agent_profile: Profile do agente alvo (ex: "ana")
        limit: Limite de sessões
        
    Returns:
        Lista de sessões
    """
    try:
        from enterprise.mcp.ana_sessions import get_pool
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            # Buscar sessões do agente
            if agent_profile == "ana" or agent_profile == "atendimento":
                rows = await conn.fetch("""
                    SELECT session_id, persona, cell, status, message_count, 
                           last_message_at, created_at
                    FROM ana_sessions
                    WHERE persona = $2 AND status = 'active'
                    ORDER BY last_message_at DESC
                    LIMIT $1
                """, limit, agent_profile)
                
                return [dict(row) for row in rows]
            
            # Para outros profiles, usar SessionDB local
            return []
    
    except Exception as e:
        logger.error("Failed to read agent sessions: %s", e)
        return []


async def read_session_messages(
    session_id: str,
    agent_profile: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Lê mensagens de uma sessão específica.
    
    Args:
        session_id: ID da sessão
        agent_profile: Profile do agente
        limit: Limite de mensagens
        
    Returns:
        Lista de mensagens
    """
    try:
        from enterprise.mcp.ana_sessions import get_pool
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT role, content, created_at, tokens_used
                FROM ana_messages
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, session_id, limit)
            
            return [dict(row) for row in reversed(rows)]
    
    except Exception as e:
        logger.error("Failed to read session messages: %s", e)
        return []


# ---------------------------------------------------------------------------
# Análise de conversas
# ---------------------------------------------------------------------------

async def analyze_conversations(
    agent_profile: str,
    sample_size: int = 10,
) -> Dict[str, Any]:
    """Analisa conversas do agente para identificar padrões.
    
    Args:
        agent_profile: Profile do agente
        sample_size: Número de sessões para analisar
        
    Returns:
        Análise com insights e sugestões
    """
    sessions = await read_agent_sessions(agent_profile, sample_size)
    
    analysis = {
        "total_sessions": len(sessions),
        "common_questions": [],
        "pain_points": [],
        "suggestions": [],
        "metrics": {
            "avg_messages_per_session": 0,
            "total_messages": 0,
            "active_clients": len(set(s.get("cell") for s in sessions)),
        },
    }
    
    # Analisar cada sessão
    all_messages = []
    for session in sessions:
        messages = await read_session_messages(
            session["session_id"], 
            agent_profile,
            limit=20,
        )
        all_messages.extend(messages)
    
    # Calcular métricas
    if all_messages:
        analysis["metrics"]["total_messages"] = len(all_messages)
        analysis["metrics"]["avg_messages_per_session"] = len(all_messages) / max(len(sessions), 1)
    
    # Identificar padrões (simplificado - em produção usar LLM)
    user_messages = [m for m in all_messages if m.get("role") == "user"]
    
    # Contar termos comuns
    term_counts = {}
    for msg in user_messages:
        content = msg.get("content", "").lower()
        for term in ["preço", "entrega", "personalização", "pedido", "pagamento"]:
            if term in content:
                term_counts[term] = term_counts.get(term, 0) + 1
    
    # Top perguntas
    analysis["common_questions"] = [
        {"topic": term, "count": count}
        for term, count in sorted(term_counts.items(), key=lambda x: -x[1])
    ][:5]
    
    return analysis


# ---------------------------------------------------------------------------
# Geração de melhorias
# ---------------------------------------------------------------------------

async def generate_improvements(
    agent_profile: str,
    analysis: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Gera sugestões de melhoria baseadas na análise.
    
    Args:
        agent_profile: Profile do agente
        analysis: Resultado da análise
        
    Returns:
        Lista de melhorias sugeridas
    """
    improvements = []
    
    # Melhorias baseadas em padrões
    for qa in analysis.get("common_questions", []):
        topic = qa["topic"]
        count = qa["count"]
        
        if count > 5:  # Pergunta frequente
            improvements.append({
                "type": "skill_patch",
                "target": "ana-atendimento",
                "description": f"Adicionar informação sobre {topic} na skill",
                "priority": "high",
                "reason": f"Cliente pergunta sobre {topic} {count} vezes",
            })
    
    # Melhorias baseadas em métricas
    metrics = analysis.get("metrics", {})
    if metrics.get("avg_messages_per_session", 0) > 10:
        improvements.append({
            "type": "config_change",
            "target": "max_iterations",
            "description": "Aumentar limite de iterações por sessão",
            "priority": "medium",
            "reason": "Sessões longas indicam necessidade de mais iterações",
        })
    
    return improvements


# ---------------------------------------------------------------------------
# Aplicação de melhorias (com audit)
# ---------------------------------------------------------------------------

async def apply_improvement(
    improvement: Dict[str, Any],
    applied_by: str = "curator",
) -> bool:
    """Aplica uma melhoria de forma auditável.
    
    Args:
        improvement: Melhoria a ser aplicada
        applied_by: Quem está aplicando (curator, admin, etc)
        
    Returns:
        True se aplicada com sucesso
    """
    try:
        from enterprise.mcp.ana_sessions import log_audit
        
        improvement_type = improvement.get("type")
        target = improvement.get("target")
        description = improvement.get("description")
        
        # Log antes de aplicar
        await log_audit(
            agent="ana",
            action=f"improvement_{improvement_type}",
            target=target,
            new_value=improvement,
            reason=description,
            created_by=applied_by,
        )
        
        # Aplicar baseado no tipo
        if improvement_type == "skill_patch":
            # Em produção: usar skill_manage para patch
            logger.info("Would apply skill patch: %s", description)
            return True
        
        elif improvement_type == "config_change":
            # Em produção: usar config_manage
            logger.info("Would apply config change: %s", description)
            return True
        
        return False
    
    except Exception as e:
        logger.error("Failed to apply improvement: %s", e)
        return False


# ---------------------------------------------------------------------------
# Loop principal do curator cross-profile
# ---------------------------------------------------------------------------

async def run_cross_profile_curator(
    target_profile: str = ANA_PROFILE,
    sample_size: int = 10,
) -> Dict[str, Any]:
    """Executa o curator cross-profile.
    
    Args:
        target_profile: Profile alvo (default: ana)
        sample_size: Tamanho da amostra para análise
        
    Returns:
        Resultado da execução
    """
    logger.info("Starting cross-profile curator for %s", target_profile)
    
    # 1. Analisar conversas
    analysis = await analyze_conversations(target_profile, sample_size)
    
    # 2. Gerar melhorias
    improvements = await generate_improvements(target_profile, analysis)
    
    # 3. Aplicar melhorias
    applied = []
    for improvement in improvements:
        success = await apply_improvement(improvement)
        if success:
            applied.append(improvement)
    
    result = {
        "target_profile": target_profile,
        "analysis": analysis,
        "improvements_suggested": len(improvements),
        "improvements_applied": len(applied),
        "applied": applied,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    logger.info(
        "Cross-profile curator completed: %d suggested, %d applied",
        len(improvements),
        len(applied),
    )
    
    return result
