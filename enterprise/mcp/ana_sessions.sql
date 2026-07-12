-- Hermes Enterprise — Schema para sessões da Ana
-- Executado automaticamente na inicialização do Postgres

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

-- Tabela de clientes (cadastro básico)
CREATE TABLE IF NOT EXISTS ana_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cell VARCHAR(20) UNIQUE NOT NULL,  -- Número do cliente
    name VARCHAR(100),  -- Nome (se fornecido)
    first_contact_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_contact_at TIMESTAMP WITH TIME ZONE,
    total_interactions INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'  -- Dados extras
);

-- Índice para clientes
CREATE INDEX IF NOT EXISTS idx_customers_cell ON ana_customers(cell);

-- Tabela de configuração da Ana (gerenciada pelo Admin)
CREATE TABLE IF NOT EXISTS ana_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by VARCHAR(100)  -- admin, curator, system
);

-- Configurações padrão da Ana
INSERT INTO ana_config (config_key, config_value, updated_by) VALUES
    ('model', '{"provider": "openai", "name": "gpt-4o-mini"}', 'system'),
    ('max_iterations', '{"value": 5}', 'system'),
    ('skills_enabled', '["ana-atendimento", "cesto-damore"]', 'system'),
    ('tools_enabled', '["send_message", "search_products", "get_product", "memory", "session_search"]', 'system')
ON CONFLICT (config_key) DO NOTHING;

-- View para estatísticas rápidas
CREATE OR REPLACE VIEW ana_stats AS
SELECT
    COUNT(DISTINCT cell) as unique_clients,
    COUNT(*) as total_sessions,
    SUM(message_count) as total_messages,
    MAX(last_message_at) as last_activity,
    AVG(message_count) as avg_messages_per_session
FROM ana_sessions
WHERE status = 'active';

-- View para sessões ativas
CREATE OR REPLACE VIEW ana_active_sessions AS
SELECT
    s.cell,
    s.session_id,
    s.message_count,
    s.last_message_at,
    c.name as customer_name
FROM ana_sessions s
LEFT JOIN ana_customers c ON s.cell = c.cell
WHERE s.status = 'active'
ORDER BY s.last_message_at DESC;
