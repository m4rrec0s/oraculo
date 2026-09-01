-- Hermes Enterprise — Schema para sessões por persona
-- Executado automaticamente na inicialização do Postgres

-- Rename legacy Ana objects only when destination objects are absent. If both
-- names exist, leave them untouched so migration cannot merge or lose data.
DO $$
BEGIN
    IF to_regclass('ana_sessions') IS NOT NULL AND to_regclass('sessions') IS NOT NULL THEN RAISE EXCEPTION 'Both ana_sessions and sessions exist'; END IF;
    IF to_regclass('ana_messages') IS NOT NULL AND to_regclass('messages') IS NOT NULL THEN RAISE EXCEPTION 'Both ana_messages and messages exist'; END IF;
    IF to_regclass('ana_customers') IS NOT NULL AND to_regclass('customers') IS NOT NULL THEN RAISE EXCEPTION 'Both ana_customers and customers exist'; END IF;
    IF to_regclass('ana_config') IS NOT NULL AND to_regclass('config') IS NOT NULL THEN RAISE EXCEPTION 'Both ana_config and config exist'; END IF;
    IF to_regclass('ana_stats') IS NOT NULL AND to_regclass('stats') IS NOT NULL THEN RAISE EXCEPTION 'Both ana_stats and stats exist'; END IF;
    IF to_regclass('ana_active_sessions') IS NOT NULL AND to_regclass('active_sessions') IS NOT NULL THEN RAISE EXCEPTION 'Both ana_active_sessions and active_sessions exist'; END IF;
    IF to_regclass('ana_sessions') IS NOT NULL AND to_regclass('sessions') IS NULL THEN
        ALTER TABLE ana_sessions RENAME TO sessions;
    END IF;
    IF to_regclass('ana_messages') IS NOT NULL AND to_regclass('messages') IS NULL THEN
        ALTER TABLE ana_messages RENAME TO messages;
    END IF;
    IF to_regclass('ana_customers') IS NOT NULL AND to_regclass('customers') IS NULL THEN
        ALTER TABLE ana_customers RENAME TO customers;
    END IF;
    IF to_regclass('ana_config') IS NOT NULL AND to_regclass('config') IS NULL THEN
        ALTER TABLE ana_config RENAME TO config;
    END IF;
    IF to_regclass('ana_stats') IS NOT NULL AND to_regclass('stats') IS NULL THEN
        ALTER VIEW ana_stats RENAME TO stats;
    END IF;
    IF to_regclass('ana_active_sessions') IS NOT NULL AND to_regclass('active_sessions') IS NULL THEN
        ALTER VIEW ana_active_sessions RENAME TO active_sessions;
    END IF;
    IF to_regclass('idx_ana_sessions_cell') IS NOT NULL AND to_regclass('idx_sessions_cell') IS NULL THEN
        ALTER INDEX idx_ana_sessions_cell RENAME TO idx_sessions_cell;
    END IF;
    IF to_regclass('idx_ana_sessions_status') IS NOT NULL AND to_regclass('idx_sessions_status') IS NULL THEN
        ALTER INDEX idx_ana_sessions_status RENAME TO idx_sessions_status;
    END IF;
    IF to_regclass('idx_ana_sessions_last_message') IS NOT NULL AND to_regclass('idx_sessions_last_message') IS NULL THEN
        ALTER INDEX idx_ana_sessions_last_message RENAME TO idx_sessions_last_message;
    END IF;
    IF to_regclass('idx_ana_sessions_persona') IS NOT NULL AND to_regclass('idx_sessions_persona') IS NULL THEN
        ALTER INDEX idx_ana_sessions_persona RENAME TO idx_sessions_persona;
    END IF;
    IF to_regclass('idx_ana_messages_session') IS NOT NULL AND to_regclass('idx_messages_session') IS NULL THEN
        ALTER INDEX idx_ana_messages_session RENAME TO idx_messages_session;
    END IF;
    IF to_regclass('idx_ana_messages_created') IS NOT NULL AND to_regclass('idx_messages_created') IS NULL THEN
        ALTER INDEX idx_ana_messages_created RENAME TO idx_messages_created;
    END IF;
    IF to_regclass('idx_ana_messages_persona') IS NOT NULL AND to_regclass('idx_messages_persona') IS NULL THEN
        ALTER INDEX idx_ana_messages_persona RENAME TO idx_messages_persona;
    END IF;
    IF to_regclass('ana_sessions_pkey') IS NOT NULL AND to_regclass('sessions_pkey') IS NULL THEN
        ALTER INDEX ana_sessions_pkey RENAME TO sessions_pkey;
    END IF;
    IF to_regclass('ana_sessions_session_id_key') IS NOT NULL AND to_regclass('sessions_session_id_key') IS NULL THEN
        ALTER INDEX ana_sessions_session_id_key RENAME TO sessions_session_id_key;
    END IF;
    IF to_regclass('ana_messages_pkey') IS NOT NULL AND to_regclass('messages_pkey') IS NULL THEN
        ALTER INDEX ana_messages_pkey RENAME TO messages_pkey;
    END IF;
    IF to_regclass('ana_customers_pkey') IS NOT NULL AND to_regclass('customers_pkey') IS NULL THEN
        ALTER INDEX ana_customers_pkey RENAME TO customers_pkey;
    END IF;
    IF to_regclass('ana_customers_cell_key') IS NOT NULL AND to_regclass('customers_cell_key') IS NULL THEN
        ALTER INDEX ana_customers_cell_key RENAME TO customers_cell_key;
    END IF;
    IF to_regclass('ana_config_pkey') IS NOT NULL AND to_regclass('config_pkey') IS NULL THEN
        ALTER INDEX ana_config_pkey RENAME TO config_pkey;
    END IF;
END $$;

-- Tabela de sessões por cliente
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona VARCHAR(50) NOT NULL DEFAULT 'atendimento',
    cell VARCHAR(20) NOT NULL,  -- Número do cliente (ex: 5583999999999)
    session_id VARCHAR(100) UNIQUE NOT NULL,  -- ID da sessão Hermes
    status VARCHAR(20) DEFAULT 'active',  -- active, archived, blocked
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE,
    message_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'  -- Dados extras do cliente
);

-- Upgrade installations created before persona-aware storage.
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS persona VARCHAR(50) NOT NULL DEFAULT 'atendimento';

-- Índices para busca rápida
CREATE INDEX IF NOT EXISTS idx_sessions_cell ON sessions(cell);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_last_message ON sessions(last_message_at);

-- Tabela de mensagens (histórico por sessão)
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona VARCHAR(50) NOT NULL DEFAULT 'atendimento',
    session_id VARCHAR(100) NOT NULL REFERENCES sessions(session_id),
    role VARCHAR(20) NOT NULL,  -- user, assistant, system
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    tokens_used INTEGER DEFAULT 0,
    tool_calls JSONB DEFAULT '[]'
);

ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS persona VARCHAR(50) NOT NULL DEFAULT 'atendimento';

-- Índices para mensagens
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_persona ON sessions(persona);
CREATE INDEX IF NOT EXISTS idx_messages_persona ON messages(persona);

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

-- Tabela de clientes (cadastro básico)
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cell VARCHAR(20) UNIQUE NOT NULL,  -- Número do cliente
    name VARCHAR(100),  -- Nome (se fornecido)
    first_contact_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_contact_at TIMESTAMP WITH TIME ZONE,
    total_interactions INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'  -- Dados extras
);

-- Índice para clientes
CREATE INDEX IF NOT EXISTS idx_customers_cell ON customers(cell);

-- Tabela de configuração (gerenciada pelo Admin)
CREATE TABLE IF NOT EXISTS config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by VARCHAR(100)  -- admin, curator, system
);

-- Configurações padrão
INSERT INTO config (config_key, config_value, updated_by) VALUES
    ('model', '{"provider": "openai", "name": "gpt-4o-mini"}', 'system'),
    ('max_iterations', '{"value": 5}', 'system'),
    ('skills_enabled', '["ana-atendimento", "cesto-damore"]', 'system'),
    ('tools_enabled', '["send_message", "search_products", "get_product", "memory", "session_search"]', 'system')
ON CONFLICT (config_key) DO NOTHING;

-- View para estatísticas rápidas
CREATE OR REPLACE VIEW stats AS
SELECT
    COUNT(DISTINCT cell) as unique_clients,
    COUNT(*) as total_sessions,
    SUM(message_count) as total_messages,
    MAX(last_message_at) as last_activity,
    AVG(message_count) as avg_messages_per_session
FROM sessions
WHERE status = 'active';

-- View para sessões ativas
CREATE OR REPLACE VIEW active_sessions AS
SELECT
    s.cell,
    s.session_id,
    s.message_count,
    s.last_message_at,
    c.name as customer_name
FROM sessions s
LEFT JOIN customers c ON s.cell = c.cell
WHERE s.status = 'active'
ORDER BY s.last_message_at DESC;
