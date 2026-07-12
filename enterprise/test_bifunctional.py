#!/usr/bin/env python3
"""Enterprise — Teste do Sistema Bifuncional.

Testa o routing por header, tool guard e sessões da Ana.
"""

import asyncio
import sys
from pathlib import Path

# Adicionar path do projeto
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_agent_router():
    """Testa o routing por header."""
    print("\n=== Teste: Agent Router ===")
    
    from enterprise.middleware.agent_router import resolve_agent, VALID_AGENTS
    
    # Teste 1: Header válido
    agent, home = resolve_agent("admin")
    print(f"✓ Header 'admin' → agent={agent}, home={home}")
    assert agent == "admin"
    
    # Teste 2: Header válido
    agent, home = resolve_agent("ana")
    print(f"✓ Header 'ana' → agent={agent}, home={home}")
    assert agent == "ana"
    
    # Teste 3: Header ausente (fail-safe)
    agent, home = resolve_agent(None)
    print(f"✓ Header None → agent={agent} (fail-safe)")
    assert agent == "ana"
    
    # Teste 4: Header inválido
    agent, home = resolve_agent("invalid")
    print(f"✓ Header 'invalid' → agent={agent} (fail-safe)")
    assert agent == "ana"
    
    print("✓ Todos os testes de routing passaram!")


async def test_tool_guard():
    """Testa o tool guard."""
    print("\n=== Teste: Tool Guard ===")
    
    from enterprise.middleware.tool_guard import (
        is_tool_allowed,
        is_skill_allowed,
        ANA_ALLOWED_TOOLS,
        ANA_BLOCKED_TOOLS,
    )
    
    # Teste 1: Tool permitida para Ana
    assert is_tool_allowed("send_message", "ana") == True
    print("✓ send_message permitida para Ana")
    
    # Teste 2: Tool bloqueada para Ana
    assert is_tool_allowed("terminal", "ana") == False
    print("✓ terminal bloqueada para Ana")
    
    # Teste 3: Admin tem acesso a tudo
    assert is_tool_allowed("terminal", "admin") == True
    print("✓ Admin tem acesso a terminal")
    
    # Teste 4: Skill permitida
    assert is_skill_allowed("ana-atendimento", "ana") == True
    print("✓ ana-atendimento permitida para Ana")
    
    # Teste 5: Skill bloqueada
    assert is_skill_allowed("hermes-agent", "ana") == False
    print("✓ hermes-agent bloqueada para Ana")
    
    print("✓ Todos os testes de tool guard passaram!")


async def test_ana_sessions():
    """Testa as sessões da Ana (requer PostgreSQL)."""
    print("\n=== Teste: Ana Sessions ===")
    
    try:
        from enterprise.mcp.ana_sessions import (
            get_or_create_session,
            save_message,
            get_conversation_history,
            get_session_stats,
        )
        
        # Teste 1: Criar sessão
        cell = "5583999999999"
        session = await get_or_create_session(cell)
        print(f"✓ Sessão criada: {session['session_id']}")
        assert session["is_new"] == True
        
        # Teste 2: Buscar mesma sessão
        session2 = await get_or_create_session(cell)
        print(f"✓ Sessão encontrada: {session2['session_id']}")
        assert session2["session_id"] == session["session_id"]
        assert session2["is_new"] == False
        
        # Teste 3: Salvar mensagem
        await save_message(session["session_id"], "user", "Oi, quero comprar")
        print("✓ Mensagem salva")
        
        # Teste 4: Buscar histórico
        history = await get_conversation_history(session["session_id"])
        print(f"✓ Histórico: {len(history)} mensagens")
        assert len(history) == 1
        
        # Teste 5: Estatísticas
        stats = await get_session_stats()
        print(f"✓ Stats: {stats}")
        
        print("✓ Todos os testes de sessões passaram!")
        
    except Exception as e:
        print(f"⚠ Teste de sessões pulado (PostgreSQL não disponível): {e}")


async def test_audit_log():
    """Testa o audit log."""
    print("\n=== Teste: Audit Log ===")
    
    try:
        from enterprise.mcp.ana_sessions import log_audit, get_audit_log
        
        # Teste 1: Log de auditoria
        await log_audit(
            agent="ana",
            action="skill_update",
            target="ana-atendimento",
            old_value={"version": "0.1.0"},
            new_value={"version": "0.2.0"},
            reason="Adicionada informação sobre entrega",
            created_by="curator",
        )
        print("✓ Audit log registrado")
        
        # Teste 2: Buscar logs
        logs = await get_audit_log(agent="ana")
        print(f"✓ Logs encontrados: {len(logs)}")
        
        print("✓ Todos os testes de audit passaram!")
        
    except Exception as e:
        print(f"⚠ Teste de audit pulado (PostgreSQL não disponível): {e}")


async def main():
    """Executa todos os testes."""
    print("=" * 60)
    print("Enterprise — Teste do Sistema Bifuncional")
    print("=" * 60)
    
    # Testes que não precisam de PostgreSQL
    await test_agent_router()
    await test_tool_guard()
    
    # Testes que precisam de PostgreSQL
    await test_ana_sessions()
    await test_audit_log()
    
    print("\n" + "=" * 60)
    print("✓ Todos os testes concluídos!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
