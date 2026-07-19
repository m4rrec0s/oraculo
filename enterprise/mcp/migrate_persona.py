#!/usr/bin/env python3
"""Enterprise — Migration: adiciona coluna persona às tabelas de sessão.

Aplica o bloco idempotente MIGRATE_SQL (DO $$ com IF NOT EXISTS) ao banco
dedicado do Hermes (HERMES_PG_*). Roda uma vez em produção para colunas
ausentes; seguro rodar múltiplas vezes.

Uso:
    python enterprise/mcp/migrate_persona.py
    HERMES_PG_HOST=... HERMES_PG_DATABASE=... python enterprise/mcp/migrate_persona.py
"""

from __future__ import annotations

import asyncio
import os

import asyncpg

# Conexão interna do swarm via DATABASE_URL (ex: postgres://...@oraculo_postgres:5432/hermes).
DATABASE_URL = os.getenv("DATABASE_URL", "")

MIGRATE_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='ana_sessions' AND column_name='persona') THEN
        ALTER TABLE ana_sessions ADD COLUMN persona VARCHAR(50) NOT NULL DEFAULT 'atendimento';
        CREATE INDEX IF NOT EXISTS idx_ana_sessions_persona ON ana_sessions(persona);
        RAISE NOTICE 'ana_sessions.persona adicionada';
    ELSE
        RAISE NOTICE 'ana_sessions.persona ja existe';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='ana_messages' AND column_name='persona') THEN
        ALTER TABLE ana_messages ADD COLUMN persona VARCHAR(50) NOT NULL DEFAULT 'atendimento';
        CREATE INDEX IF NOT EXISTS idx_ana_messages_persona ON ana_messages(persona);
        RAISE NOTICE 'ana_messages.persona adicionada';
    ELSE
        RAISE NOTICE 'ana_messages.persona ja existe';
    END IF;
END $$;
"""


async def migrate() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não definida — defina no .env da persona")
    pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(MIGRATE_SQL)
        print(f"Migration aplicada em {DATABASE_URL}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(migrate())
