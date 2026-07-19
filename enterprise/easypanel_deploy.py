#!/usr/bin/env python3
"""Enterprise — Deploy de personas via Easypanel (API tRPC).

O Easypanel NAO expoe uma REST API publica (tipo /api/project/{p}/services).
O painel fala com o backend via tRPC:

    GET/POST {EASYPANEL_URL}/api/trpc/{router}.{procedure}

- Queries (leitura)  -> GET, input vai como query string `?input=<json>`
- Mutations (escrita) -> POST, body `{"json": {...}}`

O fluxo de criacao de um servico tipo "app" (docker image) e em VARIAS
chamadas separadas, nao um payload unico:

    1. services.app.createService      (cria o servico vazio)
    2. services.app.updateSourceImage  (define a imagem docker)
    3. services.app.updateEnv          (define env vars, como string .env)
    4. services.app.updatePorts        (define portas publicadas)
    5. services.app.updateMounts       (define bind mounts, se houver)
    6. services.app.deployService      (dispara o deploy)

IMPORTANTE — leia antes de rodar em producao:
    Os nomes exatos de procedure/campos abaixo foram meu melhor esforco com
    base em documentacao de terceiros que fizeram engenharia reversa da API
    do Easypanel (nao e uma API oficial documentada). Pode haver diferencas
    de nome de campo (ex.: hostPath/mountPath vs source/target) ou de router
    dependendo da versao do seu painel (<=2.30 usa tRPC classico, >=2.31 usa
    uma camada RPC nova em /api/rpc/*).

    Antes de rodar contra producao, RECOMENDO fortemente:
    1. Rodar com --dry-run primeiro (so imprime as chamadas, nao executa).
    2. Rodar com --probe (abaixo) para descobrir a versao/API flavor do seu
       painel e validar autenticacao antes de qualquer escrita.
    3. Se algo falhar, abra o DevTools (aba Network, filtro "trpc") no
       navegador, crie/edite um servico manualmente pelo painel, e compare
       o payload real enviado com o que este script esta montando. Isso
       resolve 100% das divergencias de schema em poucos minutos.

Variaveis lidas do .env (ou ambiente):
    EASYPANEL_URL            ex: https://painel.exemplo.com
    EASYPANEL_TOKEN          token de API do Easypanel (Bearer) OU
    EASYPANEL_COOKIE         cookie de sessao completo (ex: "token=xxxx")
    EASYPANEL_PROJECT_NAME   nome do projeto no Easypanel

Uso:
    python enterprise/easypanel_deploy.py --probe        # testa conexão/versão
    python enterprise/easypanel_deploy.py                # deploy de todas em PERSONAS
    python enterprise/easypanel_deploy.py ana            # só uma persona
    python enterprise/easypanel_deploy.py --dry-run ana  # não chama a API, só mostra
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuração das personas
# ---------------------------------------------------------------------------

IMAGE = os.getenv(
    "HERMES_ENTERPRISE_IMAGE",
    "ghcr.io/m4rrec0s/oraculo/hermes-enterprise:latest",
)

HOST_VOLUME_ROOT = os.getenv("HERMES_HOST_VOLUME_ROOT", "/var/lib/hermes")

PERSONAS = [
    {
        "name": "atendimento",
        "api_port": 8001,
        "bind": True,
        "model_provider": "nvidia",
        "model_name": "nvidia/nemotron-3-super-120b-a12b",
        "model_base_url": "https://integrate.api.nvidia.com/v1",
        "disabled_toolsets": [
            "terminal", "file", "browser", "code_execution", "delegation",
            "kanban", "vision", "image_gen", "todo", "tts", "video",
            "cronjob", "hermes-cli",
        ],
        "skills": False,
    },
    {
        "name": "admin",
        "api_port": 8000,
        "bind": False,
        "model_provider": "nvidia",
        "model_name": "nvidia/nemotron-3-super-120b-a12b",
        "model_base_url": "https://integrate.api.nvidia.com/v1",
        "disabled_toolsets": [],
        "skills": True,
    },
    {
        "name": "honda-atendimento",
        "api_port": 8083,
        "bind": True,
        "model_provider": "openai",
        "model_name": "gpt-5-nano",
        "model_base_url": "https://api.openai.com/v1",
        "disabled_toolsets": [
            "terminal", "file", "browser", "code_execution", "delegation",
            "kanban", "vision", "image_gen", "todo", "tts", "video",
            "cronjob", "hermes-cli",
        ],
        "skills": False,
    },
    # Adicione novas personas aqui.
]


# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------

def load_dotenv(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        env[key.strip()] = val.strip().strip('"').strip("'")
    return env


# ---------------------------------------------------------------------------
# Cliente tRPC do Easypanel
# ---------------------------------------------------------------------------

class EasypanelTrpcClient:
    """Cliente minimo para a API tRPC (nao oficial) do Easypanel.

    Aceita autenticação por Bearer token OU por cookie de sessão — o painel
    usa cookie por padrão no navegador; alguns tokens de API funcionam via
    Authorization: Bearer. Se um não funcionar, tente o outro.
    """

    def __init__(self, base_url: str, token: str | None, cookie: str | None) -> None:
        self.base = base_url.rstrip("/")
        self.token = token
        self.cookie = cookie

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _request(self, method: str, procedure: str, payload: dict | None) -> tuple[int, dict | str | None]:
        if method == "GET":
            qs = ""
            if payload is not None:
                qs = "?" + urllib.parse.urlencode({"input": json.dumps({"json": payload})})
            url = f"{self.base}/api/trpc/{procedure}{qs}"
            data = None
        else:
            url = f"{self.base}/api/trpc/{procedure}"
            data = json.dumps({"json": payload or {}}).encode()

        req = urllib.request.Request(url, data=data, method=method, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                status = resp.status
                ctype = resp.headers.get("Content-Type", "")
                raw = resp.read().decode()
                if "application/json" not in ctype:
                    return status, raw[:300]
                return status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, body[:500]
        except urllib.error.URLError as exc:
            return -1, str(exc.reason)

    def query(self, procedure: str, payload: dict | None = None):
        status, res = self._request("GET", procedure, payload)
        return status, res

    def mutate(self, procedure: str, payload: dict | None = None):
        status, res = self._request("POST", procedure, payload)
        return status, res

    def probe(self) -> None:
        """Testa a conexão chamando um procedure de leitura simples."""
        print(f"Testando conexão com {self.base} ...")
        status, res = self.query("auth.getUser")
        print(f"  auth.getUser -> HTTP {status}")
        print(f"  {json.dumps(res, indent=2, ensure_ascii=False) if isinstance(res, dict) else res}")
        if status == 200:
            print("  OK: autenticação parece válida.")
        elif status == 401 or status == 403:
            print("  FALHOU: token/cookie inválido ou expirado.")
        elif status == 404:
            print("  AVISO: procedure não encontrado — pode ser painel >= 2.31 (API mudou para /api/rpc/*).")
        else:
            print("  Resultado inesperado, inspecione acima.")


# ---------------------------------------------------------------------------
# Montagem de payloads por persona (formato tRPC, chamadas separadas)
# ---------------------------------------------------------------------------

def build_env_string(persona: dict, extra_env: dict) -> str:
    """Easypanel armazena env como texto no formato .env, não array."""
    lines = [
        f"ENTERPRISE_PROFILE={persona['name']}",
        f"AGENT_NAME={persona['name'].capitalize()}",
        f"API_SERVER_PORT={persona['api_port']}",
        "API_SERVER_HOST=0.0.0.0",
        f"PROFILE_BIND={'1' if persona.get('bind') else '0'}",
        f"ENTERPRISE_SKILLS={'1' if persona.get('skills') else '0'}",
        f"ENTERPRISE_MINIMAL={'1' if persona.get('disabled_toolsets') else '0'}",
        f"MODEL_PROVIDER={persona.get('model_provider', 'nvidia')}",
        f"MODEL_NAME={persona.get('model_name', 'nvidia/nemotron-3-super-120b-a12b')}",
        f"MODEL_BASE_URL={persona.get('model_base_url', 'https://integrate.api.nvidia.com/v1')}",
    ]
    if extra_env.get("DATABASE_URL"):
        lines.append(f"DATABASE_URL={extra_env['DATABASE_URL']}")
    for key in ("CESTO_PG_HOST", "CESTO_PG_PORT", "CESTO_PG_DATABASE", "CESTO_PG_USER", "CESTO_PG_PASSWORD"):
        if extra_env.get(key):
            lines.append(f"{key}={extra_env[key]}")
    if persona.get("disabled_toolsets"):
        lines.append(f"DISABLED_TOOLSETS={','.join(persona['disabled_toolsets'])}")
    return "\n".join(lines)


def build_mounts(persona: dict) -> list:
    if not persona.get("bind"):
        return []
    host = f"{HOST_VOLUME_ROOT}/shared-{persona['name']}"
    # ATENCAO: campos hostPath/mountPath sao um chute educado — confirme via
    # DevTools se seu painel usa nomes diferentes (ex.: source/target).
    return [{
        "type": "bind",
        "hostPath": host,
        "mountPath": f"/home/hermes/.hermes/profiles/{persona['name']}",
    }]


def deploy_persona(client: EasypanelTrpcClient, project: str, persona: dict,
                    extra_env: dict, dry_run: bool) -> bool:
    service_name = f"hermes-{persona['name']}"
    port = persona["api_port"]
    print(f"\n=== Persona: {persona['name']} (serviço {service_name}, porta {port}) ===")

    # 1) Verifica se já existe
    inspect_payload = {"projectName": project, "serviceName": service_name}
    if dry_run:
        print("  [dry-run] inspectService:", inspect_payload)
        exists = False
    else:
        status, res = client.query("services.app.inspectService", inspect_payload)
        exists = status == 200

    # 2) Cria se necessário
    create_payload = {"projectName": project, "serviceName": service_name}
    if not exists:
        if dry_run:
            print("  [dry-run] createService:", create_payload)
        else:
            print("  Criando serviço...")
            status, res = client.mutate("services.app.createService", create_payload)
            if status != 200:
                print(f"  FALHOU ao criar serviço: HTTP {status} -> {res}")
                return False
    else:
        print("  Serviço já existe, atualizando configuração...")

    # 3) Define a imagem docker (source)
    source_payload = {
        "projectName": project,
        "serviceName": service_name,
        "image": IMAGE,
    }
    # 4) Env vars
    env_payload = {
        "projectName": project,
        "serviceName": service_name,
        "env": build_env_string(persona, extra_env),
    }
    # 5) Portas
    ports_payload = {
        "projectName": project,
        "serviceName": service_name,
        "ports": [{"published": port, "target": port, "protocol": "tcp"}],
    }
    # 6) Mounts (se houver)
    mounts = build_mounts(persona)
    mounts_payload = {
        "projectName": project,
        "serviceName": service_name,
        "mounts": mounts,
    }

    steps = [
        ("services.app.updateSourceImage", source_payload),
        ("services.app.updateEnv", env_payload),
        ("services.app.updatePorts", ports_payload),
    ]
    if mounts:
        steps.append(("services.app.updateMounts", mounts_payload))

    for procedure, payload in steps:
        if dry_run:
            print(f"  [dry-run] {procedure}:", json.dumps(payload, ensure_ascii=False))
            continue
        status, res = client.mutate(procedure, payload)
        if status != 200:
            print(f"  FALHOU em {procedure}: HTTP {status} -> {res}")
            return False
        print(f"  OK: {procedure}")

    # 7) Deploy
    deploy_payload = {"projectName": project, "serviceName": service_name}
    if dry_run:
        print("  [dry-run] deployService:", deploy_payload)
        return True

    status, res = client.mutate("services.app.deployService", deploy_payload)
    if status != 200:
        print(f"  FALHOU ao disparar deploy: HTTP {status} -> {res}")
        return False
    print("  Deploy disparado com sucesso.")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    dotenv_path = Path(os.getenv("ENTERPRISE_DOTENV", ".env"))
    env = load_dotenv(dotenv_path)
    for k, v in os.environ.items():
        if k.startswith("EASYPANEL_") or k.startswith("CESTO_PG_") or k.startswith("HERMES_PG_"):
            env.setdefault(k, v)

    url = env.get("EASYPANEL_URL") or os.getenv("EASYPANEL_URL")
    token = env.get("EASYPANEL_TOKEN") or os.getenv("EASYPANEL_TOKEN")
    cookie = env.get("EASYPANEL_COOKIE") or os.getenv("EASYPANEL_COOKIE")
    project = env.get("EASYPANEL_PROJECT_NAME") or os.getenv("EASYPANEL_PROJECT_NAME")

    if not url or not project or not (token or cookie):
        print("ERRO: defina EASYPANEL_URL, EASYPANEL_PROJECT_NAME e (EASYPANEL_TOKEN ou EASYPANEL_COOKIE).")
        return 1

    client = EasypanelTrpcClient(url, token, cookie)

    if "--probe" in sys.argv:
        client.probe()
        return 0

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv

    targets = PERSONAS
    if args:
        targets = [p for p in PERSONAS if p["name"] in args]
        if not targets:
            print(f"Nenhuma persona corresponde a: {args}")
            return 1

    extra_env = {
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "CESTO_PG_HOST": os.getenv("CESTO_PG_HOST", ""),
        "CESTO_PG_PORT": os.getenv("CESTO_PG_PORT", ""),
        "CESTO_PG_DATABASE": os.getenv("CESTO_PG_DATABASE", ""),
        "CESTO_PG_USER": os.getenv("CESTO_PG_USER", ""),
        "CESTO_PG_PASSWORD": os.getenv("CESTO_PG_PASSWORD", ""),
    }

    ok_count = 0
    for persona in targets:
        if deploy_persona(client, project, persona, extra_env, dry_run):
            ok_count += 1

    print(f"\nConcluído: {ok_count}/{len(targets)} personas processadas com sucesso.")
    return 0 if ok_count == len(targets) else 1


if __name__ == "__main__":
    raise SystemExit(main())