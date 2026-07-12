# Enterprise — Hermes Bifuncional

Sistema com dois agentes independentes operando na mesma base de código.

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    HERMES INFRAESTRUTURA                     │
│                                                             │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │ Hermes Default   │    │           Ana                    │ │
│  │ (Admin/Control)  │    │       (Atendimento)              │ │
│  │                  │    │                                   │ │
│  │ • CLI/Dashboard  │    │ • WhatsApp (HTTP API)            │ │
│  │ • Stats negócio  │    │ • Skills: ana-atendimento.*      │ │
│  │ • Cria skills    │    │ • Tools: apenas comunicacional   │ │
│  │ • Cria regras    │    │ • Memória: POR CLIENTE (cell)    │ │
│  │ • Aprende global │    │ • Sessão: isolada por cliente    │ │
│  │ • Melhora Ana    │    │ • Zero auto-modificação          │ │
│  └─────────────────┘    └─────────────────────────────────┘ │
│                                                             │
│  Headers: X-Hermes-Agent: admin | ana                       │
└─────────────────────────────────────────────────────────────┘
```

## Setup

### 1. Configurar Profiles

```bash
cd hermes-agent
python enterprise/setup_profiles.py all
```

Isso cria:
- `~/.hermes/` — Profile Admin (config padrão)
- `~/.hermes/profiles/ana/` — Profile Ana (restrito)

### 2. Configurar API Keys

**Admin:**
```bash
# Editar ~/.hermes/.env
NVIDIA_API_KEY=xxx
OPENAI_API_KEY=xxx
```

**Ana:**
```bash
# Editar ~/.hermes/profiles/ana/.env
OPENAI_API_KEY=xxx
WHATSAPP_TOKEN=xxx
WHATSAPP_PHONE_ID=xxx
```

### 3. Configurar PostgreSQL

```bash
# Conectar ao PostgreSQL existente ou criar novo
# O schema já está em enterprise/mcp/ana_sessions.py

# Executar setup do schema:
python -c "
import asyncio
from enterprise.mcp.ana_sessions import init_schema
asyncio.run(init_schema())
"
```

### 4. Iniciar Serviços

```bash
# Com Docker
docker-compose -f docker-compose.enterprise.yml --profile admin --profile atendimento up

# Ou manualmente
# Terminal 1: Admin
HERMES_PROFILE=admin hermes gateway

# Terminal 2: Ana
HERMES_PROFILE=ana hermes gateway --port 5001
```

## Uso

### Headers HTTP

Toda requisição HTTP deve incluir o header `X-Hermes-Agent`:

```bash
# Para Admin (controle total)
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "X-Hermes-Agent: admin" \
  -H "Authorization: Bearer admin-key" \
  -d '{"messages": [{"role": "user", "content": "Mostre estatísticas"}]}'

# Para Ana (atendimento)
curl -X POST http://localhost:8082/v1/chat/completions \
  -H "X-Hermes-Agent: ana" \
  -d '{"messages": [{"role": "user", "content": "Oi, quero comprar"}]}'

# Header ausente → Ana (fail-safe)
curl -X POST http://localhost:8082/v1/chat/completions \
  -d '{"messages": [{"role": "user", "content": "Oi"}]}'
```

### WhatsApp (Ana)

O WhatsApp webhook recebe mensagens e roteia para a Ana:

```bash
# Webhook do WhatsApp
POST https://your-domain.com/webhooks/whatsapp

# Header automático: X-Hermes-Agent: ana
```

### CLI

```bash
# Usar como Admin
hermes -p admin chat

# Usar como Ana
hermes -p ana chat
```

## Isolamento

### Por Agente

| Aspecto | Admin | Ana |
|---------|-------|-----|
| **HERMES_HOME** | `~/.hermes/` | `~/.hermes/profiles/ana/` |
| **Config** | Completa | Restrita |
| **Skills** | Todas | Apenas atendimento |
| **Tools** | Todas | Comunicacionais |
| **Memória** | Global | Por cliente |
| **Sessão** | Persistent | Stateless |

### Por Cliente (Ana)

Cada cliente (cell) tem:
- Session ID único: `ana-{cell}-{uuid}`
- Histórico isolado no PostgreSQL
- Memória de conversa específica

Exemplo:
```sql
-- Sessão do cliente 5583999999999
SELECT * FROM ana_sessions WHERE cell = '5583999999999';

-- Mensagens dessa sessão
SELECT * FROM ana_messages WHERE session_id = 'ana-5583999999999-abc123';
```

## Segurança

### Fail-Safe Restritivo

- Header ausente → Ana (menos permissivo)
- Header inválido → Ana
- Qualquer ambiguidade → Ana

### Isolamento de Escrita

- Ana NÃO pode modificar suas próprias skills
- Ana NÃO pode acessar tools administrativas
- Ana NÃO pode ver memória de outros clientes

### Audit Log

Toda mudança autônoma fica registrada:

```sql
SELECT * FROM hermes_audit_log 
WHERE agent = 'ana' 
ORDER BY created_at DESC;
```

## Arquivos

```
enterprise/
├── mcp/
│   ├── erp_server.py          # Servidor ERP (Produtos, Pedidos)
│   ├── whatsapp_server.py     # Servidor WhatsApp
│   └── ana_sessions.py        # Sessões da Ana (PostgreSQL)
├── middleware/
│   ├── agent_router.py        # Routing por header
│   └── tool_guard.py          # Restrição de tools
├── learning/
│   └── cross_profile_curator.py  # Aprendizado cross-profile
├── setup_profiles.py          # Setup de profiles
└── README.md                  # Este arquivo
```

## Próximos Passos

1. [ ] Integrar agent_router no gateway principal
2. [ ] Configurar webhook WhatsApp para Ana
3. [ ] Implementar dashboard de métricas da Ana
4. [ ] Configurar cron para cross-profile learning
5. [ ] Adicionar alertas de audit log

## Comandos Úteis

```bash
# Verificar profiles
hermes profile list

# Verificar sessões da Ana
python -c "
import asyncio
from enterprise.mcp.ana_sessions import get_session_stats
print(asyncio.run(get_session_stats()))
"

# Ver audit log
python -c "
import asyncio
from enterprise.mcp.ana_sessions import get_audit_log
logs = asyncio.run(get_audit_log())
for log in logs[:10]:
    print(f\"{log['created_at']}: {log['action']} on {log['target']}\")
"
```
