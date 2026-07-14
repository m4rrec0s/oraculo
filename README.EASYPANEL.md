# Hermes Enterprise — Easypanel Deployment Guide

> Deploy Hermes (Admin + Ana) no Easypanel com PostgreSQL e Redis gerenciados externamente.

## 📋 Pré-requisitos

- Conta Easypanel (testado em **Contabo VPS - França** com Easypanel 2.8+)
- Token de API permanente do Easypanel (veja seção **"Gerar Token de API"** abaixo)
- Variáveis de ambiente: `EASYPANEL_URL`, `EASYPANEL_TOKEN` (ou usar arquivo `.env`)
- Node.js 20+ (para rodar o script de provisioning)

## 🔑 Gerar Token de API do Easypanel

### Opção 1: Via CLI (recomendado)

Se você tem acesso à linha de comando do servidor Easypanel:

```bash
# SSH no servidor
ssh user@easypanel-host

# Ir para o diretório Easypanel
cd /opt/easypanel

# Gerar token (via script interno)
docker exec $(docker ps -q -f label=com.docker.compose.service=easypanel) \
  npm run cli -- users.generateApiToken <user-id>
```

### Opção 2: Via Dashboard Easypanel

1. Faça login no Dashboard Easypanel (`https://seu-easypanel.host`)
2. Vá para **Settings > Users** (ou similar)
3. Procure por "API Token" ou "Generate Token"
4. Copie o token e adicione ao seu `.env`:

```bash
EASYPANEL_TOKEN=seu-token-aqui
EASYPANEL_URL=https://seu-easypanel.host
```

## 🚀 Deployment em 4 Passos

### Step 1: Configurar Variáveis de Ambiente

```bash
# Clone ou acesse o repositório
cd Cesto\ Agent

# Copie o arquivo de exemplo
cp .env.easypanel.example .env

# Edite com suas credenciais
# - EASYPANEL_URL
# - EASYPANEL_TOKEN
# - NVIDIA_API_KEY
# - OPENAI_API_KEY
nano .env
```

### Step 2: Rodar Script de Provisionamento

O script `easypanel-provision.ts` faz **tudo automaticamente**:
- Cria projeto `oraculo`
- Provisiona PostgreSQL 16
- Provisiona Redis 7
- Cria serviços `hermes-admin` e `hermes-atendimento`
- Gera senhas seguras
- Conecta tudo automaticamente

```bash
# Via npm (se tiver scripts configurados)
npm run provision:easypanel

# Ou diretamente com npx
npx tsx scripts/easypanel-provision.ts

# Ou com node se compilado
node scripts/easypanel-provision.js
```

**Saída esperada:**

```
[2026-07-14T...] ===================================================================
[2026-07-14T...] Easypanel Provisioning: Oraculo (Hermes Enterprise)
[2026-07-14T...] ===================================================================
[2026-07-14T...] URL: https://seu-easypanel.host
[2026-07-14T...] Token: xxxx...xxxx
[2026-07-14T...] Project: oraculo

[2026-07-14T...] STEP 1/5: Provisioning project
[2026-07-14T...] ✓ Project provisioned
...
[2026-07-14T...] ✓ PROVISIONING COMPLETE
```

Um arquivo `.easypanel-provision-output.json` será criado com todas as credenciais.

### Step 3: Verificar Status no Dashboard

Acesse seu Dashboard Easypanel e confirme:

1. ✅ Projeto `oraculo` existe
2. ✅ Serviço `postgres` está rodando
3. ✅ Serviço `redis` está rodando
4. ✅ Serviço `hermes-admin` está rodando (porta 8081 → dashboard, 9119 → admin)
5. ✅ Serviço `hermes-atendimento` está rodando (porta 8082)

### Step 4: Testar Conectividade

```bash
# De fora do Easypanel, teste a API do Admin
curl -X GET http://seu-easypanel-host:8081/health \
  -H "Authorization: Bearer $(cat .env | grep ADMIN_API_KEY | cut -d= -f2)"

# Teste a API da Ana
curl -X GET http://seu-easypanel-host:8082/health \
  -H "Authorization: Bearer $(cat .env | grep ANA_API_KEY | cut -d= -f2)"
```

## 📊 Arquitetura

```
Easypanel Project: oraculo
├── PostgreSQL (container isolado)
│   ├── Host: oraculo_postgres:5432
│   └── Database: hermes
├── Redis (container isolado)
│   ├── Host: oraculo_redis:6379
│   └── Persistence: disabled (ephemeral)
└── Hermes Network (bridge)
    ├── hermes-admin
    │   ├── porta 8081 (API)
    │   └── porta 9119 (Dashboard)
    └── hermes-atendimento (Ana)
        └── porta 8082 (API)
```

Todos os containers compartilham a mesma rede interna do projeto, permitindo comunicação via hostname: `oraculo_postgres`, `oraculo_redis`.

## 🔄 Idempotência & Reruns

O script é totalmente **idempotente**:

```bash
# Rodar duas vezes resulta no mesmo estado final
npm run provision:easypanel
npm run provision:easypanel  # <- sem duplicações, sem erro
```

- Se projeto/postgres/redis já existem, são pulados
- Se apps já existem, são pulados
- Credenciais existentes NÃO são regeneradas (preserve `.easypanel-provision-output.json`)

## 🛠️ Troubleshooting

### "EASYPANEL_TOKEN environment variable is not set"

```bash
export EASYPANEL_TOKEN=seu-token
export EASYPANEL_URL=https://seu-easypanel.host
npm run provision:easypanel
```

Ou adicione ao `.env`:

```env
EASYPANEL_TOKEN=seu-token
EASYPANEL_URL=https://seu-easypanel.host
```

### "tRPC call failed: projects.listProjects"

1. Verifique que `EASYPANEL_URL` está correto (sem trailing slash)
2. Verifique que `EASYPANEL_TOKEN` é válido (gerado via `users.generateApiToken`)
3. Teste conectividade: `curl https://seu-easypanel.host/api/health`

### Hermes containers não conseguem conectar ao PostgreSQL

1. Confirme que o serviço PostgreSQL está saudável no Dashboard
2. Verifique credenciais em `.env`: `HERMES_PG_HOST`, `HERMES_PG_PASSWORD`
3. Confira logs do container: `docker logs hermes-admin`
4. Script tem retry automático (18 tentativas, 10s cada) — aguarde

### "Cannot connect to Redis"

1. Verifique que o serviço Redis está rodando no Dashboard
2. Confirme hostname em `.env`: `HERMES_REDIS_HOST` (padrão: `oraculo_redis`)
3. Se Redis requer senha, certifique-se que está em `HERMES_REDIS_PASSWORD`

## 🔐 Segurança

### Credenciais Geradas

O script gera **senhas aleatórias de 32 caracteres** para PostgreSQL e Redis:
- Armazenadas em `.easypanel-provision-output.json`
- Também visíveis no Dashboard Easypanel (uma única vez na criação)
- **Nunca são regeneradas** em reruns — preserve o arquivo

### Variáveis Sensíveis

⚠️ **NÃO commite na repo:**

```gitignore
.env
.easypanel-provision-output.json
```

Ambos já estão em `.gitignore`. Se não estiverem:

```bash
echo ".env" >> .gitignore
echo ".easypanel-provision-output.json" >> .gitignore
git add .gitignore && git commit -m "update: ensure .env and provision output are ignored"
```

## 📝 Notas Técnicas

### Por que Easypanel?

- ✅ Não exige conhecimento de Kubernetes
- ✅ Suporta volumes persistentes
- ✅ Rede interna para serviços comunicarem
- ✅ Dashboard para monitoring
- ✅ Backup automático (opcional)
- ✅ Custo baixo em VPS compartilhado

### PostgreSQL & Redis Externo

**Vantagens:**
- Compartilhados com outros apps do projeto
- Backup centralizado
- Upgrade independente de Hermes
- Replica de produção

**Desvantagens:**
- Hermes não sobe offline (BD externo obrigatório)
- Retry on boot (script aguarda 180s máximo)
- Se BD cai, Hermes fica inacessível

### Retry Logic

No `docker/enterprise-entrypoint.sh`:

```bash
# Tenta conectar ao Postgres 18 vezes, com 10s entre tentativas (180s total)
for i in $(seq 1 18); do
    if python3 -c "import pg8000; pg8000.connect(...)"
    then ensured=1; break
    else sleep 10
    fi
done
```

## 🚢 Development vs Production

### Local (com docker-compose.dev.yml)

```bash
docker-compose -f docker-compose.dev.yml up -d
```

Postgres/Redis inclusos (ephemeral).

### Easypanel (com docker-compose.easypanel.yml)

```bash
docker-compose -f docker-compose.easypanel.yml up -d
```

Postgres/Redis externos (via Easypanel).

## 📞 Suporte

Se o script falhar:

1. Verifique logs: `cat .easypanel-provision-output.json | jq`
2. Teste tRPC manualmente:
   ```bash
   curl -X POST https://seu-easypanel.host/api/trpc/projects.listProjects \
     -H "Authorization: Bearer $EASYPANEL_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"json":{}}'
   ```
3. Fallback: Configure manualmente via Dashboard Easypanel UI

---

**Última atualização:** 2026-07-14  
**Versão do Script:** 1.0  
**Tested on:** Easypanel 2.8+, Contabo VPS (France)
