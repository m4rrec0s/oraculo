# Hermes Autodeploy — Trigger Easypanel Webhooks

> Dispare automaticamente o redeploy dos serviços Hermes no Easypanel

## 🚀 Configuração

### Webhooks Configurados

```
Admin:       http://185.205.246.213:3000/api/deploy/3a4abf2c67756fd6712e642f95b43e3afaeb69447b1d73a2
Atendimento: http://185.205.246.213:3000/api/deploy/ce1d1e068927681fce50e871683c48aa77bc87a4d47312ee
```

## 📋 Como Usar

### Opção 1: Via NPM Scripts (Recomendado)

```bash
# Deploy apenas admin
npm run autodeploy:hermes:admin

# Deploy apenas atendimento
npm run autodeploy:hermes:atendimento

# Deploy ambos (com delay de 2s entre eles)
npm run autodeploy:hermes:all
```

### Opção 2: Via Script Bash Direto

```bash
# Deploy admin
./scripts/autodeploy-hermes.sh admin

# Deploy atendimento
./scripts/autodeploy-hermes.sh atendimento

# Deploy ambos
./scripts/autodeploy-hermes.sh both
```

### Opção 3: Via Curl Manual

```bash
# Admin
curl -X POST http://185.205.246.213:3000/api/deploy/3a4abf2c67756fd6712e642f95b43e3afaeb69447b1d73a2

# Atendimento
curl -X POST http://185.205.246.213:3000/api/deploy/ce1d1e068927681fce50e871683c48aa77bc87a4d47312ee
```

## 🔄 Autodeploy Automático ao Iniciar

### Opção A: Manual (Recomendado para agora)

Após containers subirem:

```bash
# Aguarde 2 minutos
sleep 120

# Dispare o autodeploy
npm run autodeploy:hermes:all
```

### Opção B: Automático no Docker-compose (Avançado)

Descomente as linhas `command:` em `docker-compose.easypanel.yml`:

**Para hermes-admin:**
```yaml
command: >
  sh -c "
  python3 -m hermes gateway &
  sleep 120 &&
  curl -X POST http://185.205.246.213:3000/api/deploy/3a4abf2c67756fd6712e642f95b43e3afaeb69447b1d73a2
  "
```

**Para hermes-atendimento:**
```yaml
command: >
  sh -c "
  python3 -m hermes gateway &
  sleep 120 &&
  curl -X POST http://185.205.246.213:3000/api/deploy/ce1d1e068927681fce50e871683c48aa77bc87a4d47312ee
  "
```

**Não recomendado porque:**
- Bloqueia o container
- Difícil debugar se algo falhar
- Precisa de `curl` instalado na imagem

## 📊 Status da Resposta

Webhook bem-sucedido retorna:

```
HTTP/1.1 200 OK
{"status": "triggered", "deployment_id": "..."}
```

Se receber 404 ou 500:
- Verifique se a URL está correta
- Confirme se o webhook não expirou
- Teste manualmente: `curl -v <webhook-url>`

## 🎯 Workflow Completo

```bash
# 1. Levantar containers com DATABASE_URL e REDIS_URL
docker-compose -f docker-compose.easypanel.yml up -d

# 2. Aguardar inicialização (min 2 minutos)
sleep 120

# 3. Dispare o autodeploy
npm run autodeploy:hermes:all

# 4. Acompanhe o deployment no Dashboard Easypanel
# ou via logs: docker-compose logs -f
```

## 🔍 Troubleshooting

### "Connection refused"

```bash
# Verifique se o IP/URL está correto
ping 185.205.246.213

# Teste com curl
curl -v http://185.205.246.213:3000/api/deploy/3a4abf2c67756fd6712e642f95b43e3afaeb69447b1d73a2
```

### "Webhook expired"

- Webhooks podem ter validade limitada
- Gere um novo webhook no Easypanel se necessário
- Atualizar URLs em `scripts/autodeploy-hermes.sh` e `.env`

### "Container não responde"

```bash
# Verifique saúde do container
docker-compose ps

# Veja logs
docker-compose logs hermes-admin

# Aguarde mais tempo
sleep 180
npm run autodeploy:hermes:admin
```

## 📝 Arquivo de Configuração

As URLs estão em:
- `scripts/autodeploy-hermes.sh` — variáveis `ADMIN_WEBHOOK` e `ATENDIMENTO_WEBHOOK`

Para alterar:
```bash
nano scripts/autodeploy-hermes.sh
# Edite as variáveis no topo
```

## ✅ Verificação

Após dispare o autodeploy:

```bash
# Check deployment status
docker-compose ps

# Check logs
docker-compose logs --tail=50 hermes-admin
docker-compose logs --tail=50 hermes-atendimento

# Check if services are healthy
curl http://localhost:8081/health
curl http://localhost:8082/health
```

---

**Pronto!** Agora seus containers Hermes se atualizam automaticamente via webhooks Easypanel! 🚀
