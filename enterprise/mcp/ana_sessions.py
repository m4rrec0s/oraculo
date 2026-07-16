"""Enterprise — Sessões da Ana por cliente (cell).

Gerencia sessões stateful da Ana no PostgreSQL.
Cada cliente (cell) tem sua própria sessão com histórico isolado.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

# Configuração via env (mesmo padrão do erp_server.py)
PG_HOST = os.getenv("CESTO_PG_HOST", "easypanel.cestodamore.com.br")
PG_PORT = int(os.getenv("CESTO_PG_PORT", "54320"))
PG_DATABASE = os.getenv("CESTO_PG_DATABASE", "cesto_damore")
PG_USER = os.getenv("CESTO_PG_USER", "postgres")
PG_PASSWORD = os.getenv("CESTO_PG_PASSWORD", "")
PG_SSL = os.getenv("CESTO_PG_SSL", "false").lower() == "true"

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Obtém pool de conexões PostgreSQL."""
    global _pool
    if _pool is None or _pool.is_closed():
        _pool = await asyncpg.create_pool(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            ssl=PG_SSL,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool() -> None:
    """Fecha pool de conexões."""
    global _pool
    if _pool and not _pool.is_closed():
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Schema SQL (executar uma vez para criar as tabelas)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Tabela de sessões da Ana por cliente
CREATE TABLE IF NOT EXISTS ana_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cell VARCHAR(20) NOT NULL,  -- Número do cliente (ex: 5583999999999)
    session_id VARCHAR(100) UNIQUE NOT NULL,  -- ID da sessão Hermes
    status VARCHAR(20) DEFAULT 'active',  -- active, archived, blocked
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE,
    message_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'  -- Dados extras do cliente
);

-- Índices para busca rápida
CREATE INDEX IF NOT EXISTS idx_ana_sessions_cell ON ana_sessions(cell);
CREATE INDEX IF NOT EXISTS idx_ana_sessions_status ON ana_sessions(status);
CREATE INDEX IF NOT EXISTS idx_ana_sessions_last_message ON ana_sessions(last_message_at);

-- Tabela de mensagens da Ana (histórico por sessão)
CREATE TABLE IF NOT EXISTS ana_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL REFERENCES ana_sessions(session_id),
    role VARCHAR(20) NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tokens_used INTEGER DEFAULT 0,
    tool_calls JSONB DEFAULT '[]'
);

-- Índices para mensagens
CREATE INDEX IF NOT EXISTS idx_ana_messages_session ON ana_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_ana_messages_created ON ana_messages(created_at);

-- Tabela de audit log para mudanças autônomas
CREATE TABLE IF NOT EXISTS hermes_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent VARCHAR(50) NOT NULL,  -- admin, ana
    action VARCHAR(100) NOT NULL,  -- skill_update, config_change, etc
    target VARCHAR(100),  -- skill_name, config_key, etc
    old_value JSONB,
    new_value JSONB,
    reason TEXT,  -- Motivo da mudança
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by VARCHAR(100)  -- user, admin, cron, curator
);

-- Índices para audit
CREATE INDEX IF NOT EXISTS idx_audit_agent ON hermes_audit_log(agent);
CREATE INDEX IF NOT EXISTS idx_audit_action ON hermes_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_created ON hermes_audit_log(created_at);
"""


async def init_schema() -> None:
    """Cria tabelas se não existirem."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


# ---------------------------------------------------------------------------
# Sessões da Ana
# ---------------------------------------------------------------------------

async def get_or_create_session(cell: str, name: str = None) -> Dict[str, Any]:
    """Busca ou cria sessão para o cliente (cell).
    
    Retorna dict com session_id e metadata.
    """
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Buscar sessão ativa existente
        row = await conn.fetchrow("""
            SELECT session_id, status, metadata, created_at
            FROM ana_sessions
            WHERE cell = $1 AND status = 'active'
            ORDER BY last_message_at DESC NULLS LAST
            LIMIT 1
        """, cell)
        
        if row:
            # Atualizar timestamp
            await conn.execute("""
                UPDATE ana_sessions
                SET last_message_at = NOW(), updated_at = NOW()
                WHERE session_id = $1
            """, row["session_id"])
            
            return {
                "session_id": row["session_id"],
                "status": row["status"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"].isoformat(),
                "is_new": False,
            }
        
        # Criar nova sessão
        import uuid
        session_id = f"ana-{cell}-{uuid.uuid4().hex[:8]}"
        
        await conn.execute("""
            INSERT INTO ana_sessions (cell, session_id, status, metadata)
            VALUES ($1, $2, 'active', $3)
        """, cell, session_id, json.dumps({"name": name}) if name else "{}")
        
        return {
            "session_id": session_id,
            "status": "active",
            "metadata": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_new": True,
        }


async def save_message(
    session_id: str,
    role: str,
    content: str,
    tokens_used: int = 0,
    tool_calls: List[Dict] = None,
) -> None:
    """Salva mensagem na sessão."""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ana_messages (session_id, role, content, tokens_used, tool_calls)
            VALUES ($1, $2, $3, $4, $5)
        """, session_id, role, content, tokens_used, json.dumps(tool_calls or []))
        
        # Atualizar contadores da sessão
        await conn.execute("""
            UPDATE ana_sessions
            SET message_count = message_count + 1,
                last_message_at = NOW(),
                updated_at = NOW()
            WHERE session_id = $1
        """, session_id)


async def get_conversation_history(
    session_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Busca histórico de mensagens da sessão."""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content, created_at, tokens_used, tool_calls
            FROM ana_messages
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, session_id, limit)
        
        # Inverter para ordem cronológica
        messages = []
        for row in reversed(rows):
            messages.append({
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"].isoformat(),
                "tokens_used": row["tokens_used"],
                "tool_calls": json.loads(row["tool_calls"]) if row["tool_calls"] else [],
            })
        
        return messages


async def archive_session(session_id: str) -> None:
    """Arquiva sessão (não deleta)."""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE ana_sessions
            SET status = 'archived', updated_at = NOW()
            WHERE session_id = $1
        """, session_id)


async def get_session_stats(cell: str = None) -> Dict[str, Any]:
    """Retorna estatísticas das sessões."""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        if cell:
            row = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_sessions,
                    SUM(message_count) as total_messages,
                    MAX(last_message_at) as last_activity
                FROM ana_sessions
                WHERE cell = $1
            """, cell)
        else:
            row = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_sessions,
                    SUM(message_count) as total_messages,
                    COUNT(DISTINCT cell) as unique_clients,
                    MAX(last_message_at) as last_activity
                FROM ana_sessions
            """)
        
        return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

async def log_audit(
    agent: str,
    action: str,
    target: str = None,
    old_value: Any = None,
    new_value: Any = None,
    reason: str = None,
    created_by: str = "system",
) -> None:
    """Registra mudança no audit log."""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO hermes_audit_log (agent, action, target, old_value, new_value, reason, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, agent, action, target,
            json.dumps(old_value) if old_value else None,
            json.dumps(new_value) if new_value else None,
            reason, created_by)


async def get_audit_log(
    agent: str = None,
    action: str = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Busca audit log."""
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        query = "SELECT * FROM hermes_audit_log WHERE 1=1"
        params = []
        
        if agent:
            query += " AND agent = $1"
            params.append(agent)
        
        if action:
            query += " AND action = $2" if params else " AND action = $1"
            params.append(action)
        
        query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)
        
        rows = await conn.fetch(query, *params)
        
        return [dict(row) for row in rows]
