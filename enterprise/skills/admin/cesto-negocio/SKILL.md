name: cesto-negocio
description: Gerencia Cesto d'Amore — stats, resumo diário e edição da Ana.
metadata:
  hermes:
    tags: [cesto, negocio, ana, stats, resumo]
    category: business
    related_skills: [autoaprendizado-ana]
---

# Cesto d'Amore — Gestão de Negócio

Skill do Hermes Admin para gerir a Cesto d'Amore: estatísticas, resumo diário e supervisão/edição da Ana (atendente).

## When to Use
- Gerar estatísticas de pedidos, receita e clientes a partir da API.
- Enviar resumo diário via WhatsApp (WaHa) ou Telegram.
- Avaliar a qualidade do atendimento da Ana.
- Editar a persona, config ou skills da Ana (Managing Profile).

## Prerequisites
- Env vars (`.env`): `CESTO_API_URL`, `CESTO_API_EMAIL`, `CESTO_API_PASSWORD`, `WAHA_API_URL`, `WAHA_API_KEY`, `WAHA_INSTANCE`, `WHATSAPP_GROUP_ID`.
- Ferramentas: `terminal` (curl/python3), `web_extract`, `read_file`, `patch`, `write`, `cronjob`.

## API Cesto d'Amore
Base: `https://api.cestodamore.com.br` (porta 3333).

**Toda requisição exige o header `x-api-key`** (valor em `CESTO_API_KEY` no `.env`). Autenticação JWT por cima.

Login:
```
POST /auth/login  body: {"email","password"}  → { token }
Headers: x-api-key: <CESTO_API_KEY>  ;  Authorization: Bearer <token> (demais chamadas)
```
Endpoints úteis:
- `GET /orders?limit=500` — lista pedidos (filtrar por `createdAt` para o dia).
- `GET /orders/:id` — detalhe de pedido.
- `GET /agent-logs/stats` — estatísticas do agente (requer admin).
- `GET /admin/coupons/:id/stats` — stats de cupom.

Exemplo (via `terminal`):
```
TOKEN=$(curl -s -X POST "$CESTO_API_URL/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$CESTO_API_EMAIL\",\"password\":\"$CESTO_API_PASSWORD\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
curl -s "$CESTO_API_URL/orders?limit=500" -H "Authorization: Bearer $TOKEN"
```

## Resumo Diário
Use `scripts/daily_summary.py` (carrega env vars, autentica, busca pedidos do dia, calcula stats, envia via WaHa):
```
python3 scripts/daily_summary.py            # envia
python3 scripts/daily_summary.py --dry-run  # só imprime
```
Formato: data · total de pedidos · receita · novos clientes · principais dúvidas · alertas. Enviado ao grupo WhatsApp (`WHATSAPP_GROUP_ID`) via WaHa `POST /api/{WAHA_INSTANCE}/sendText`.

Agendar com `cronjob`:
```
hermes cron add "0 8 * * *" --prompt "Gere o resumo diário da Cesto d'Amore e envie via WaHa/Telegram" --skill cesto-negocio
```

## Edição da Ana (Managing Profile)
Os arquivos da Ana ficam montados em `/managed/ana/`:
- Persona: `/managed/ana/SOUL.md`
- Config: `/managed/ana/config.yaml`
- Skills: `/managed/ana/skills/`

Para ajustar: `read_file` → `patch`/`write` → documentar a mudança. A Ana aplica na próxima sessão (sem reinício de container). Nunca quebre as Regras de Ouro (redirecionamento ao site; não inventar cestas; não fechar venda).

## Avaliação da Ana
- Revise sessões recentes (`session_search` ou `/agent-logs/stats` da API).
- Métricas: taxa de redirecionamento ao site, dúvidas não resolvidas, satisfação.
- Ao detectar padrão recorrente, aperfeiçoe a Ana (edite `SOUL.md`/`config.yaml` ou acrescente FAQ via skill `autoaprendizado-ana`).

## Pitfalls
- Não exponha `WAHA_API_KEY`, senha do dono, chave PIX, dados bancários nem Endereço completo.
- Não invente dados do negócio — baseie em números da API.
- `chatId` de grupo WhatsApp termina com `@g.us`.

## Verification
- `python3 scripts/daily_summary.py --dry-run` imprime o resumo sem enviar.
- Edição de `/managed/ana/SOUL.md` reflete na próxima sessão da Ana.
