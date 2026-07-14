"""Enterprise CLI — Comandos slash e gestão de perfis."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import click
import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from enterprise.permissions.manager import PermissionManager, ProfileType, Profile
from enterprise.config.settings import get_enterprise_config
from enterprise.crm.client import CRMClient
from enterprise.learning.engine import LearningEngine

logger = structlog.get_logger()
console = Console()

# ==================== PERFIL COMMANDS ====================

@click.group(name="enterprise")
def enterprise_group() -> None:
    """Comandos Enterprise — Cesto d'Amore."""
    pass


@enterprise_group.group(name="profile")
def profile_group() -> None:
    """Gerenciamento de perfis."""
    pass


@profile_group.command("list")
def profile_list() -> None:
    """Lista perfis disponíveis."""
    pm = PermissionManager()
    profiles = pm.list_profiles()
    
    table = Table(title="🏢 Perfis Enterprise", border_style="magenta")
    table.add_column("Nome", style="bold")
    table.add_column("Display")
    table.add_column("Descrição")
    table.add_column("Tools", style="dim")
    table.add_column("Skills", style="dim")
    table.add_column("Platforms", style="dim")
    
    for p in profiles:
        tools_count = len(p.get_allowed_tools())
        skills_count = len(p.get_allowed_skills())
        platforms = ", ".join(p.gateway_platforms) if p.gateway_platforms else "—"
        
        table.add_row(
            p.name.value,
            p.display_name,
            p.description[:50] + "..." if len(p.description) > 50 else p.description,
            str(tools_count),
            str(skills_count),
            platforms,
        )
    
    console.print(table)


@profile_group.command("show")
@click.argument("profile_name", type=click.Choice([p.value for p in ProfileType]))
def profile_show(profile_name: str) -> None:
    """Mostra detalhes de um perfil."""
    pm = PermissionManager()
    profile = pm.get_profile(ProfileType(profile_name))
    
    if not profile:
        console.print(f"[red]Perfil não encontrado: {profile_name}[/red]")
        return
    
    data = profile.to_dict()
    console.print(Panel.fit(
        json.dumps(data, indent=2, ensure_ascii=False),
        title=f"[magenta]Perfil: {profile.display_name}[/magenta]",
        border_style="magenta"
    ))


@profile_group.command("activate")
@click.argument("profile_name", type=click.Choice([p.value for p in ProfileType]))
def profile_activate(profile_name: str) -> None:
    """Ativa um perfil."""
    pm = PermissionManager()
    success = pm.set_current_profile(ProfileType(profile_name))
    
    if success:
        profile = pm.get_profile(ProfileType(profile_name))
        console.print(f"[green]✅ Perfil ativado: {profile.display_name}[/green]")
    else:
        console.print(f"[red]❌ Falha ao ativar perfil: {profile_name}[/red]")


@profile_group.command("current")
def profile_current() -> None:
    """Mostra perfil atual."""
    pm = PermissionManager()
    current = pm.get_current_profile()
    
    if current:
        console.print(f"[magenta]Perfil ativo: {current.display_name} ({current.name.value})[/magenta]")
    else:
        console.print("[yellow]Nenhum perfil ativo[/yellow]")


# ==================== PERMISSÕES ====================

@enterprise_group.group(name="perm")
def perm_group() -> None:
    """Verificação de permissões."""
    pass


@perm_group.command("tool")
@click.argument("tool_name")
@click.option("--profile", type=click.Choice([p.value for p in ProfileType]), help="Perfil (padrão: atual)")
def perm_tool(tool_name: str, profile: str | None) -> None:
    """Verifica se tool é permitida."""
    pm = PermissionManager()
    ptype = ProfileType(profile) if profile else None
    allowed = pm.check_tool_permission(tool_name, ptype)
    
    profile_name = ptype.value if ptype else "atual"
    color = "green" if allowed else "red"
    status = "PERMITIDA" if allowed else "NEGADA"
    
    console.print(f"[{color}]Tool '{tool_name}' para perfil '{profile_name}': {status}[/{color}]")


@perm_group.command("skill")
@click.argument("skill_name")
@click.option("--profile", type=click.Choice([p.value for p in ProfileType]), help="Perfil (padrão: atual)")
def perm_skill(skill_name: str, profile: str | None) -> None:
    """Verifica se skill é permitida."""
    pm = PermissionManager()
    ptype = ProfileType(profile) if profile else None
    allowed = pm.check_skill_permission(skill_name, ptype)
    
    profile_name = ptype.value if ptype else "atual"
    color = "green" if allowed else "red"
    status = "PERMITIDA" if allowed else "NEGADA"
    
    console.print(f"[{color}]Skill '{skill_name}' para perfil '{profile_name}': {status}[/{color}]")


@perm_group.command("mcp")
@click.argument("mcp_name")
@click.option("--tool", help="Tool específica do MCP")
@click.option("--profile", type=click.Choice([p.value for p in ProfileType]), help="Perfil (padrão: atual)")
def perm_mcp(mcp_name: str, tool: str | None, profile: str | None) -> None:
    """Verifica se MCP é permitido."""
    pm = PermissionManager()
    ptype = ProfileType(profile) if profile else None
    allowed = pm.check_mcp_permission(mcp_name, tool, ptype)
    
    profile_name = ptype.value if ptype else "atual"
    tool_str = f" / tool: {tool}" if tool else ""
    color = "green" if allowed else "red"
    status = "PERMITIDO" if allowed else "NEGADO"
    
    console.print(f"[{color}]MCP '{mcp_name}'{tool_str} para perfil '{profile_name}': {status}[/{color}]")


# ==================== CRM ====================

@enterprise_group.group(name="crm")
def crm_group() -> None:
    """Operações CRM."""
    pass


@crm_group.command("customer")
@click.argument("phone")
def crm_customer(phone: str) -> None:
    """Busca cliente por telefone."""
    import asyncio
    
    async def _get() -> None:
        crm = CRMClient()
        try:
            customer = await crm.get_customer(phone)
            if customer:
                console.print(Panel.fit(
                    json.dumps({
                        "phone": customer.phone,
                        "name": customer.name,
                        "email": customer.email,
                        "tags": customer.tags,
                        "total_orders": customer.total_orders,
                        "total_spent": customer.total_spent,
                        "last_order": customer.last_order_date,
                    }, indent=2, ensure_ascii=False),
                    title=f"[magenta]Cliente: {phone}[/magenta]"
                ))
            else:
                console.print(f"[yellow]Cliente não encontrado: {phone}[/yellow]")
        finally:
            await crm.close()
    
    asyncio.run(_get())


@crm_group.command("conversations")
@click.argument("phone")
@click.option("--limit", default=20, help="Limite de conversas")
def crm_conversations(phone: str, limit: int) -> None:
    """Histórico de conversas do cliente."""
    import asyncio
    
    async def _get() -> None:
        crm = CRMClient()
        try:
            convs = await crm.get_customer_conversations(phone, limit)
            if not convs:
                console.print(f"[yellow]Nenhuma conversa para {phone}[/yellow]")
                return
            
            table = Table(title=f"💬 Conversas: {phone}", border_style="magenta")
            table.add_column("Sessão", style="dim")
            table.add_column("Início")
            table.add_column("Fim")
            table.add_column("Msgs")
            table.add_column("Categoria")
            table.add_column("Sentimento")
            table.add_column("Resultado")
            
            for c in convs:
                table.add_row(
                    c.session_id[:20] + "...",
                    c.started_at.strftime("%d/%m %H:%M"),
                    c.ended_at.strftime("%H:%M") if c.ended_at else "—",
                    str(c.message_count),
                    c.category or "—",
                    c.sentiment or "—",
                    c.outcome or "—",
                )
            
            console.print(table)
        finally:
            await crm.close()
    
    asyncio.run(_get())


# ==================== LEARNING ====================

@enterprise_group.group(name="learn")
def learn_group() -> None:
    """Sistema de autoaprendizado."""
    pass


@learn_group.command("analyze")
@click.option("--days", default=7, help="Dias para analisar")
def learn_analyze(days: int) -> None:
    """Analisa sessões e gera propostas."""
    import asyncio
    
    async def _analyze() -> None:
        engine = LearningEngine()
        console.print(f"[cyan]Analisando últimos {days} dias...[/cyan]")
        proposals = await engine.analyze_sessions(days)
        
        if proposals:
            console.print(f"[green]✅ {len(proposals)} propostas geradas[/green]")
            for p in proposals:
                console.print(f"  - {p.title} ({p.change_type.value}) - confiança: {p.confidence:.0%}")
        else:
            console.print("[yellow]Nenhuma proposta gerada (dados insuficientes ou sem padrões)[/yellow]")
    
    asyncio.run(_analyze())


@learn_group.command("proposals")
@click.option("--status", type=click.Choice([s.value for s in LearningStatus]), help="Filtrar por status")
def learn_proposals(status: str | None) -> None:
    """Lista propostas de aprendizado."""
    engine = LearningEngine()
    st = LearningStatus(status) if status else None
    proposals = engine.get_proposals(st)
    
    if not proposals:
        console.print("[yellow]Nenhuma proposta encontrada[/yellow]")
        return
    
    table = Table(title="📚 Propostas de Aprendizado", border_style="magenta")
    table.add_column("ID", style="dim")
    table.add_column("Tipo")
    table.add_column("Alvo")
    table.add_column("Título")
    table.add_column("Confiança", justify="right")
    table.add_column("Status")
    table.add_column("Criado")
    
    for p in proposals:
        table.add_row(
            p.id[:12] + "...",
            p.change_type.value,
            p.target,
            p.title[:40] + "..." if len(p.title) > 40 else p.title,
            f"{p.confidence:.0%}",
            p.status.value,
            p.created_at.strftime("%d/%m %H:%M"),
        )
    
    console.print(table)


@learn_group.command("approve")
@click.argument("proposal_id")
@click.option("--by", default="admin", help="Quem aprova")
def learn_approve(proposal_id: str, by: str) -> None:
    """Aprova proposta para deploy."""
    engine = LearningEngine()
    success = engine.approve_proposal(proposal_id, by)
    
    if success:
        console.print(f"[green]✅ Proposta {proposal_id} aprovada por {by}[/green]")
    else:
        console.print(f"[red]❌ Falha ao aprovar {proposal_id}[/red]")


@learn_group.command("deploy")
@click.argument("proposal_id")
def learn_deploy(proposal_id: str) -> None:
    """Deploya proposta aprovada."""
    engine = LearningEngine()
    success = engine.deploy_proposal(proposal_id)
    
    if success:
        console.print(f"[green]✅ Proposta {proposal_id} deployada com sucesso[/green]")
    else:
        console.print(f"[red]❌ Falha no deploy de {proposal_id}[/red]")


@learn_group.command("rollback")
@click.argument("proposal_id")
def learn_rollback(proposal_id: str) -> None:
    """Rollback de proposta deployada."""
    engine = LearningEngine()
    success = engine.rollback_proposal(proposal_id)
    
    if success:
        console.print(f"[green]✅ Rollback de {proposal_id} realizado[/green]")
    else:
        console.print(f"[red]❌ Falha no rollback de {proposal_id}[/red]")


# ==================== CONFIG ====================

@enterprise_group.group(name="config")
def config_group() -> None:
    """Configuração Enterprise."""
    pass


# ==================== PERSONA ====================

@enterprise_group.group(name="persona")
def persona_group() -> None:
    """Gerenciamento de persona (SOUL.md) dos profiles."""
    pass


@persona_group.command("show")
@click.argument("profile", type=str, default="atendimento")
def persona_show(profile: str) -> None:
    """Mostra persona atual do profile."""
    from enterprise.edit_service import EditService

    service = EditService(profile)
    content, err = service.get_persona()

    if err:
        console.print(f"[red]❌ {err}[/red]")
        return

    console.print(Panel(content, title=f"[magenta]Persona — {profile}[/magenta]", expand=False))


@persona_group.command("edit")
@click.argument("profile", type=str, default="atendimento")
def persona_edit(profile: str) -> None:
    """Abre editor para modificar a persona do profile."""
    import subprocess
    import tempfile
    from enterprise.edit_service import EditService

    service = EditService(profile)
    content, err = service.get_persona()

    if err:
        console.print(f"[red]❌ {err}[/red]")
        return

    # Abre editor
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        temp_path = f.name

    try:
        subprocess.run([editor, temp_path], check=False)
        new_content = Path(temp_path).read_text(encoding="utf-8")
    finally:
        Path(temp_path).unlink(missing_ok=True)

    # Aplica mudança via service
    result = service.edit_persona(new_content, trigger_reload=True)

    if result.success:
        console.print(f"[green]✅ {result.message}[/green]")
        if result.backup_path:
            console.print(f"   Backup: {result.backup_path}")
        if result.reload_triggered:
            console.print("[cyan]   Gateway recarregado (novas conversas refletem a mudança)[/cyan]")
    else:
        console.print(f"[red]❌ {result.message}[/red]")


# ==================== SKILL ====================

@enterprise_group.group(name="skill")
def skill_group() -> None:
    """Gerenciamento de skills dos profiles."""
    pass


@skill_group.command("list")
@click.argument("profile", type=str, default="atendimento")
def skill_list(profile: str) -> None:
    """Lista skills disponíveis no profile."""
    from enterprise.edit_service import EditService

    service = EditService(profile)
    skills = service.list_skills()

    if not skills:
        console.print(f"[yellow]⚠️  Nenhuma skill encontrada no profile '{profile}'[/yellow]")
        return

    table = Table(title=f"🎯 Skills — {profile}", border_style="cyan")
    table.add_column("Nome", style="bold")

    for skill_name in skills:
        table.add_row(skill_name)

    console.print(table)


@skill_group.command("show")
@click.argument("profile", type=str, default="atendimento")
@click.argument("skill_name", type=str, required=True)
def skill_show(profile: str, skill_name: str) -> None:
    """Mostra conteúdo de uma skill."""
    from enterprise.edit_service import EditService

    service = EditService(profile)
    content, err = service.get_skill(skill_name)

    if err:
        console.print(f"[red]❌ {err}[/red]")
        return

    console.print(Panel(content, title=f"[magenta]Skill: {skill_name}[/magenta]", expand=False))


@skill_group.command("edit")
@click.argument("profile", type=str, default="atendimento")
@click.argument("skill_name", type=str, required=True)
def skill_edit(profile: str, skill_name: str) -> None:
    """Abre editor para modificar uma skill."""
    import subprocess
    import tempfile
    from enterprise.edit_service import EditService

    service = EditService(profile)
    content, err = service.get_skill(skill_name)

    if err:
        console.print(f"[red]❌ {err}[/red]")
        return

    # Abre editor
    editor = os.environ.get("EDITOR", "vi")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        temp_path = f.name

    try:
        subprocess.run([editor, temp_path], check=False)
        new_content = Path(temp_path).read_text(encoding="utf-8")
    finally:
        Path(temp_path).unlink(missing_ok=True)

    # Aplica mudança via service
    result = service.edit_skill(skill_name, new_content, trigger_reload=True)

    if result.success:
        console.print(f"[green]✅ {result.message}[/green]")
        if result.backup_path:
            console.print(f"   Backup: {result.backup_path}")
        if result.reload_triggered:
            console.print("[cyan]   Gateway recarregado (novas conversas refletem a mudança)[/cyan]")
    else:
        console.print(f"[red]❌ {result.message}[/red]")


@config_group.command("validate")
def config_validate() -> None:
    """Valida configuração enterprise."""
    cfg = get_enterprise_config()
    errors = cfg.validate()
    
    if errors:
        console.print("[red]❌ Erros de configuração:[/red]")
        for err in errors:
            console.print(f"  - {err}")
    else:
        console.print("[green]✅ Configuração válida[/green]")


@config_group.command("show")
@click.option("--section", help="Seção específica (crm, learning, mcp, etc.)")
def config_show(section: str | None) -> None:
    """Mostra configuração (sem secrets)."""
    cfg = get_enterprise_config()
    data = cfg.model_dump()
    
    # Remover secrets
    def sanitize(d: dict) -> dict:
        result = {}
        for k, v in d.items():
            if any(s in k.lower() for s in ["key", "token", "password", "secret"]):
                result[k] = "***REDACTED***"
            elif isinstance(v, dict):
                result[k] = sanitize(v)
            elif isinstance(v, list):
                result[k] = [sanitize(i) if isinstance(i, dict) else i for i in v]
            else:
                result[k] = v
        return result
    
    data = sanitize(data)
    
    if section:
        data = {section: data.get(section, {})}
    
    console.print(Panel.fit(
        json.dumps(data, indent=2, ensure_ascii=False),
        title="[magenta]Config Enterprise[/magenta]"
    ))


# ==================== REGISTRATION ====================

def register_enterprise_commands(cli_group: click.Group) -> None:
    """Registra comandos enterprise no CLI principal do Hermes."""
    cli_group.add_command(enterprise_group)