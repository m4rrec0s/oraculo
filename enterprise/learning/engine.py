"""Enterprise Learning System — Autoaprendizado via análise de sessões.

Fluxo:
1. Cron job analisa sessões do perfil 'atendimento'
2. LLM identifica padrões de sucesso/falha
3. Gera propostas de atualização de skills
4. Admin aprova/rejeita via dashboard
5. Deploy com versionamento e rollback
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class LearningStatus(str, Enum):
    """Status de uma proposta de aprendizado."""
    PENDING = "pending"      # aguardando análise
    ANALYZED = "analyzed"    # analisada, aguardando aprovação
    APPROVED = "approved"    # aprovada pelo admin
    REJECTED = "rejected"    # rejeitada
    DEPLOYED = "deployed"    # em produção
    ROLLED_BACK = "rolled_back"  # rollback feito


class ChangeType(str, Enum):
    """Tipo de mudança proposta."""
    SKILL_CONTENT = "skill_content"      # alteração no conteúdo da skill
    SKILL_TRIGGERS = "skill_triggers"    # alteração nos gatilhos
    NEW_SKILL = "new_skill"              # nova skill
    PROMPT_RULE = "prompt_rule"          # regra no system prompt
    GUARDRAIL = "guardrail"              # guardrail novo/alterado


@dataclass
class SessionInsight:
    """Insight extraído de uma sessão."""
    session_id: str
    phone: str
    category: str
    success: bool
    user_message: str
    ana_response: str
    tools_used: list[str]
    skills_used: list[str]
    iterations: int
    latency_ms: float
    timestamp: datetime
    insight_type: str  # "success_pattern", "failure_pattern", "missing_knowledge", "guardrail_trigger"
    description: str
    suggested_action: str


@dataclass
class LearningProposal:
    """Proposta de atualização baseada em insights agregados."""
    id: str
    change_type: ChangeType
    target: str  # nome da skill, "system_prompt", "guardrails"
    title: str
    description: str
    current_content: str
    proposed_content: str
    reasoning: str
    supporting_insights: list[SessionInsight]
    confidence: float  # 0-1
    status: LearningStatus = LearningStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    analyzed_at: datetime | None = None
    approved_at: datetime | None = None
    deployed_at: datetime | None = None
    approved_by: str | None = None
    version: int = 1
    rollback_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "change_type": self.change_type.value,
            "target": self.target,
            "title": self.title,
            "description": self.description,
            "current_content": self.current_content,
            "proposed_content": self.proposed_content,
            "reasoning": self.reasoning,
            "supporting_insights_count": len(self.supporting_insights),
            "confidence": self.confidence,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "approved_by": self.approved_by,
            "version": self.version,
            "rollback_version": self.rollback_version,
        }


class LearningEngine:
    """Motor de autoaprendizado do Hermes Enterprise."""

    def __init__(
        self,
        config_dir: Path | None = None,
        analyzer_model: str = "gpt-4o",
        min_sessions: int = 50,
        max_daily_updates: int = 3,
    ) -> None:
        self.config_dir = config_dir or Path.home() / ".hermes" / "enterprise" / "learning"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.analyzer_model = analyzer_model
        self.min_sessions = min_sessions
        self.max_daily_updates = max_daily_updates
        self.proposals_file = self.config_dir / "proposals.json"
        self.insights_file = self.config_dir / "insights.jsonl"
        self.audit_file = self.config_dir / "audit.log"
        self.version_history: dict[str, list[dict]] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Carrega estado persistido."""
        if self.proposals_file.exists():
            with open(self.proposals_file, encoding="utf-8") as f:
                data = json.load(f)
                # Reconstruir objetos se necessário
        if self.insights_file.exists():
            # Insights são append-only JSONL
            pass

    def _save_proposals(self) -> None:
        """Salva propostas no disco."""
        proposals_data = [p.to_dict() for p in self._proposals.values()]
        with open(self.proposals_file, "w", encoding="utf-8") as f:
            json.dump(proposals_data, f, indent=2, ensure_ascii=False)

    def record_session_result(
        self,
        session_id: str,
        phone: str,
        category: str,
        success: bool,
        user_message: str,
        ana_response: str,
        tools_used: list[str],
        skills_used: list[str],
        iterations: int,
        latency_ms: float,
    ) -> None:
        """Registra resultado de sessão para análise futura."""
        insight = SessionInsight(
            session_id=session_id,
            phone=phone,
            category=category,
            success=success,
            user_message=user_message[:500],
            ana_response=ana_response[:500],
            tools_used=tools_used,
            skills_used=skills_used,
            iterations=iterations,
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            insight_type="success_pattern" if success else "failure_pattern",
            description="",
            suggested_action="",
        )
        # Append to JSONL
        with open(self.insights_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "session_id": insight.session_id,
                "phone": insight.phone,
                "category": insight.category,
                "success": insight.success,
                "user_message": insight.user_message,
                "ana_response": insight.ana_response,
                "tools_used": insight.tools_used,
                "skills_used": insight.skills_used,
                "iterations": insight.iterations,
                "latency_ms": insight.latency_ms,
                "timestamp": insight.timestamp.isoformat(),
                "insight_type": insight.insight_type,
            }, ensure_ascii=False) + "\n")

    async def analyze_sessions(self, days_back: int = 7) -> list[LearningProposal]:
        """Analisa sessões recentes e gera propostas de melhoria."""
        # Ler insights dos últimos N dias
        cutoff = datetime.now() - timedelta(days=days_back)
        insights = []
        
        if self.insights_file.exists():
            with open(self.insights_file, encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    ts = datetime.fromisoformat(data["timestamp"])
                    if ts >= cutoff:
                        insights.append(SessionInsight(**data))

        if len(insights) < self.min_sessions:
            logger.info("learning.insufficient_data", count=len(insights), min=self.min_sessions)
            return []

        # Agrupar por categoria e tipo
        from collections import defaultdict
        by_category = defaultdict(list)
        for insight in insights:
            by_category[insight.category].append(insight)

        proposals = []
        for category, cat_insights in by_category.items():
            if len(cat_insights) < 10:
                continue
            
            # Analisar padrões de falha
            failures = [i for i in cat_insights if not i.success]
            if len(failures) >= 5:
                proposal = await self._analyze_failure_pattern(category, failures)
                if proposal:
                    proposals.append(proposal)

            # Analisar padrões de sucesso para replicar
            successes = [i for i in cat_insights if i.success]
            if len(successes) >= 10:
                proposal = await self._analyze_success_pattern(category, successes)
                if proposal:
                    proposals.append(proposal)

        # Limitar propostas por dia
        today_proposals = [p for p in self._proposals.values() 
                          if p.created_at.date() == datetime.now().date() 
                          and p.status in (LearningStatus.PENDING, LearningStatus.ANALYZED)]
        
        if len(today_proposals) >= self.max_daily_updates:
            proposals = proposals[:self.max_daily_updates - len(today_proposals)]

        for proposal in proposals:
            self._proposals[proposal.id] = proposal
        
        self._save_proposals()
        return proposals

    async def _analyze_failure_pattern(
        self, category: str, failures: list[SessionInsight]
    ) -> LearningProposal | None:
        """Analisa padrão de falhas e sugere correção."""
        # Preparar contexto para LLM
        failure_examples = "\n\n".join([
            f"Cliente: {f.user_message}\nAna: {f.ana_response}\nTools: {f.tools_used}\nSkills: {f.skills_used}"
            for f in failures[:10]
        ])

        prompt = f"""Analise estas falhas da Ana (atendente Cesto d'Amore) na categoria "{category}".

FALHAS:
{failure_examples}

REGRAS DA ANA:
- Nunca fechar venda (redirecionar pro site)
- Não inventar preços/prazos
- Não fazer curadoria
- Tom informal, caloroso, máximo 2 emojis
- Redirecionar pro site: https://www.cestodamore.com.br

Identifique o padrão de falha e sugira UMA alteração concreta em:
1. Skill existente (qual skill, que trecho mudar)
2. Nova skill necessária
3. Regra de guardrail
4. Prompt do system prompt

Responda JSON:
{{
  "change_type": "skill_content|skill_triggers|new_skill|prompt_rule|guardrail",
  "target": "nome_da_skill_ou_system_prompt_ou_guardrails",
  "title": "Título curto da mudança",
  "description": "Descrição do problema e solução",
  "current_content": "trecho atual que precisa mudar (ou 'N/A')",
  "proposed_content": "novo conteúdo proposto",
  "reasoning": "Por que isso resolve o padrão de falha",
  "confidence": 0.85
}}"""

        # Aqui chamaria o LLM analyzer_model
        # Por enquanto, retorna None para implementação posterior
        logger.info("learning.failure_analysis_pending", category=category, count=len(failures))
        return None

    async def _analyze_success_pattern(
        self, category: str, successes: list[SessionInsight]
    ) -> LearningProposal | None:
        """Analisa padrões de sucesso para replicar."""
        logger.info("learning.success_analysis_pending", category=category, count=len(successes))
        return None

    def approve_proposal(self, proposal_id: str, approved_by: str) -> bool:
        """Aprova uma proposta de aprendizado."""
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != LearningStatus.ANALYZED:
            return False
        
        proposal.status = LearningStatus.APPROVED
        proposal.approved_at = datetime.now()
        proposal.approved_by = approved_by
        self._save_proposals()
        self._audit(f"APPROVE {proposal_id} by {approved_by}")
        return True

    def reject_proposal(self, proposal_id: str, reason: str) -> bool:
        """Rejeita uma proposta."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False
        
        proposal.status = LearningStatus.REJECTED
        proposal.reasoning += f"\n\nREJEITADO: {reason}"
        self._save_proposals()
        self._audit(f"REJECT {proposal_id}: {reason}")
        return True

    def deploy_proposal(self, proposal_id: str) -> bool:
        """Deploya proposta aprovada — aplica mudança real."""
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != LearningStatus.APPROVED:
            return False

        # Backup versão atual
        self._backup_current_version(proposal.target)
        
        # Aplicar mudança (delegar para skill loader, prompt builder, etc.)
        success = self._apply_change(proposal)
        
        if success:
            proposal.status = LearningStatus.DEPLOYED
            proposal.deployed_at = datetime.now()
            proposal.rollback_version = proposal.version
            proposal.version += 1
            self._save_proposals()
            self._audit(f"DEPLOY {proposal_id} v{proposal.version}")
            return True
        else:
            proposal.status = LearningStatus.REJECTED
            self._save_proposals()
            self._audit(f"DEPLOY_FAILED {proposal_id}")
            return False

    def rollback_proposal(self, proposal_id: str) -> bool:
        """Faz rollback de uma proposta deployada."""
        proposal = self._proposals.get(proposal_id)
        if not proposal or proposal.status != LearningStatus.DEPLOYED:
            return False
        
        if proposal.rollback_version is None:
            return False

        success = self._restore_version(proposal.target, proposal.rollback_version)
        
        if success:
            proposal.status = LearningStatus.ROLLED_BACK
            self._save_proposals()
            self._audit(f"ROLLBACK {proposal_id} to v{proposal.rollback_version}")
            return True
        return False

    def _backup_current_version(self, target: str) -> None:
        """Faz backup da versão atual antes de deploy."""
        # Implementar: copiar skill/file atual para version_history
        pass

    def _apply_change(self, proposal: LearningProposal) -> bool:
        """Aplica a mudança no sistema real."""
        # Implementar baseado no change_type:
        # - skill_content: reescrever arquivo .md da skill
        # - skill_triggers: atualizar triggers no skill registry
        # - new_skill: criar novo arquivo .md
        # - prompt_rule: atualizar prompt_builder.py
        # - guardrail: atualizar guardrails.py
        logger.info("learning.apply_change", proposal_id=proposal.id, target=proposal.target)
        return True  # placeholder

    def _restore_version(self, target: str, version: int) -> bool:
        """Restaura versão anterior."""
        logger.info("learning.restore_version", target=target, version=version)
        return True  # placeholder

    def _audit(self, message: str) -> None:
        """Registra no log de auditoria."""
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {message}\n")

    def get_proposals(self, status: LearningStatus | None = None) -> list[LearningProposal]:
        """Lista propostas, opcionalmente filtradas por status."""
        proposals = list(self._proposals.values())
        if status:
            proposals = [p for p in proposals if p.status == status]
        return sorted(proposals, key=lambda p: p.created_at, reverse=True)

    # Storage interno
    _proposals: dict[str, LearningProposal] = {}


# Singleton
learning_engine = LearningEngine()