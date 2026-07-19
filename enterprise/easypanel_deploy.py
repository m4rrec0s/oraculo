#!/usr/bin/env python3
"""Enterprise — Deploy de personas via Easypanel.

Cria/atualiza um serviço Docker (imagem hermes-enterprise) por persona no
Easypanel. Cada persona roda como um container isolado com seu próprio
ENTERPRISE_PROFILE, porta de api_server e volume/bind.

Variáveis lidas do .env (ou ambiente):
    EASYPANEL_URL            ex: https://painel.exemplo.com
    EASYPANEL_TOKEN          token de API do Easypanel
    EASYPANEL_PROJECT_NAME   nome do projeto no Easypanel

Uso:
    python enterprise/easypanel_deploy.py            # deploy de todas em PERSONAS
    python enterprise/easypanel_deploy.py ana        # só uma persona
    python enterprise/easypanel_deploy.py --dry-run  # não chama a API

A lista de personas vive em PERSONAS (abaixo). Cada entrada:
    name:        nome da persona (== ENTERPRISE_PROFILE)
    api_port:    porta do api_server (evitar conflito entre containers)
    bind:        True se o profile dir é um volume compartilhado (tipo atendimento)
    volume_host: caminho no host (usado quando bind=True)
    model_provider / model_name / model_base_url: override de modelo
    disabled_toolsets: lista de toolsets a bloquear (minimal)
    skills:      True para habilitar skills bundled (ex: admin)
"""

from __future__ import annotations

import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuração das personas
# ---------------------------------------------------------------------------

IMAGE = os.getenv(
    "HERMES_ENTERPRISE_IMAGE",
    "ghcr.io/m4rrec0s/oraculo/hermes-enterprise:latest",
)

# Volume base compartilhado no host (Easypanel). Cada bind de persona monta
# /var/lib/hermes/shared-<name> -> /home/hermes/.hermes/profiles/<name>
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
        "name": "hermes-honda-atendimento",
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
    # Adicione novas personas aqui. Ex:
    # {
    #     "name": "vendas",
    #     "api_port": 8084,
    #     "bind": True,
    #     "model_provider": "openai",
    #     "model_name": "gpt-5-nano",
    #     "model_base_url": "https://api.openai.com/v1",
    #     "disabled_toolsets": ["terminal", "file"],
    #     "skills": False,
    # },
]


# ---------------------------------------------------------------------------
# .env loader (mínimo: KEY=VALUE, ignore comentários e linhas vazias)
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
# Easypanel API client
# ---------------------------------------------------------------------------

class EasypanelClient:
    def __init__(self, base_url: str, token: str, project: str) -> None:
        self.base = base_url.rstrip("/")
        self.token = token
        self.project = project

    def _req(self, method: str, path: str, body: dict | None = None) -> dict | None:
        url = f"{self.base}/api{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:500]
            print(f"  [HTTP {exc.code}] {path}: {detail}")
            return None
        except urllib.error.URLError as exc:
            print(f"  [ERR] {path}: {exc.reason}")
            return None

    def list_services(self) -> list:
        res = self._req("GET", f"/project/{self.project}/services")
        if isinstance(res, dict):
            return res.get("data", res.get("services", []))
        return res or []

    def service_exists(self, name: str) -> bool:
        return any(s.get("name") == name for s in self.list_services())

    def create_service(self, payload: dict) -> dict | None:
        return self._req("POST", f"/project/{self.project}/services", payload)

    def update_service(self, name: str, payload: dict) -> dict | None:
        return self._req("PUT", f"/project/{self.project}/services/{name}", payload)

    def deploy_service(self, name: str) -> dict | None:
        return self._req("POST", f"/project/{self.project}/services/{name}/deploy")


# ---------------------------------------------------------------------------
# Montagem do payload por persona
# ---------------------------------------------------------------------------

def build_env(persona: dict) -> list:
    env = [
        {"name": "ENTERPRISE_PROFILE", "value": persona["name"]},
        {"name": "AGENT_NAME", "value": persona["name"].capitalize()},
        {"name": "API_SERVER_PORT", "value": str(persona["api_port"])},
        {"name": "API_SERVER_HOST", "value": "0.0.0.0"},
        {"name": "PROFILE_BIND", "value": "1" if persona.get("bind") else "0"},
        {"name": "ENTERPRISE_SKILLS", "value": "1" if persona.get("skills") else "0"},
        {"name": "ENTERPRISE_MINIMAL", "value": "1" if persona.get("disabled_toolsets") else "0"},
        {"name": "MODEL_PROVIDER", "value": persona.get("model_provider", "nvidia")},
        {"name": "MODEL_NAME", "value": persona.get("model_name", "nvidia/nemotron-3-super-120b-a12b")},
        {"name": "MODEL_BASE_URL", "value": persona.get("model_base_url", "https://integrate.api.nvidia.com/v1")},
        # Conexão interna do swarm (banco de sessões do Hermes)
        {"name": "DATABASE_URL", "value": os.getenv("DATABASE_URL", "")},
    ]
    # CESTO_PG_* repassado para o hermes fazer verificações do e-commerce (não sessões)
    if os.getenv("CESTO_PG_HOST"):
        env.append({"name": "CESTO_PG_HOST", "value": os.getenv("CESTO_PG_HOST", "")})
        env.append({"name": "CESTO_PG_PORT", "value": os.getenv("CESTO_PG_PORT", "")})
        env.append({"name": "CESTO_PG_DATABASE", "value": os.getenv("CESTO_PG_DATABASE", "")})
        env.append({"name": "CESTO_PG_USER", "value": os.getenv("CESTO_PG_USER", "")})
        env.append({"name": "CESTO_PG_PASSWORD", "value": os.getenv("CESTO_PG_PASSWORD", "")})
    if persona.get("disabled_toolsets"):
        env.append({
            "name": "DISABLED_TOOLSETS",
            "value": ",".join(persona["disabled_toolsets"]),
        })
    return env


def build_mounts(persona: dict) -> list:
    if not persona.get("bind"):
        return []
    host = f"{HOST_VOLUME_ROOT}/shared-{persona['name']}"
    return [{
        "type": "bind",
        "source": host,
        "target": f"/home/hermes/.hermes/profiles/{persona['name']}",
    }]


def build_payload(persona: dict) -> dict:
    name = f"hermes-{persona['name']}"
    port = persona["api_port"]
    return {
        "type": "dockerimage",
        "name": name,
        "appName": name,
        "image": IMAGE,
        "env": build_env(persona),
        "ports": [{"published": port, "target": port, "protocol": "tcp"}],
        "mounts": build_mounts(persona),
        "memoryLimit": 2048,
        "cpuLimit": 200,
        "restartPolicy": "always",
        "command": "",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    dotenv_path = Path(os.getenv("ENTERPRISE_DOTENV", ".env"))
    env = load_dotenv(dotenv_path)
    # env do sistema tem prioridade
    for k, v in os.environ.items():
        if k.startswith("EASYPANEL_") or k.startswith("CESTO_PG_") or k.startswith("HERMES_PG_"):
            env.setdefault(k, v)

    url = env.get("EASYPANEL_URL") or os.getenv("EASYPANEL_URL")
    token = env.get("EASYPANEL_TOKEN") or os.getenv("EASYPANEL_TOKEN")
    project = env.get("EASYPANEL_PROJECT_NAME") or os.getenv("EASYPANEL_PROJECT_NAME")

    if not (url and token and project):
        print("ERRO: defina EASYPANEL_URL, EASYPANEL_TOKEN e EASYPANEL_PROJECT_NAME (.env ou ambiente).")
        return 1

    # Filtrar personas pelo arg (se dado)
    targets = PERSONAS
    if len(sys.argv) > 1 and sys.argv[1] != "--dry-run":
        targets = [p for p in PERSONAS if p["name"] in sys.argv[1:]]
        if not targets:
            print(f"Nenhuma persona corresponde a: {sys.argv[1:]}")
            return 1

    dry_run = "--dry-run" in sys.argv
    client = EasypanelClient(url, token, project)

    for persona in targets:
        name = f"hermes-{persona['name']}"
        payload = build_payload(persona)
        print(f"\n=== Persona: {persona['name']} (serviço {name}, porta {persona['api_port']}) ===")
        if dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            continue
        if client.service_exists(name):
            print(f"  Atualizando serviço existente...")
            res = client.update_service(name, payload)
        else:
            print(f"  Criando novo serviço...")
            res = client.create_service(payload)
        if res is None:
            print(f"  FALHOU ao criar/atualizar {name}")
            continue
        print(f"  Serviço configurado. Disparando deploy...")
        dep = client.deploy_service(name)
        print(f"  Deploy: {'OK' if dep is not None else 'FALHOU'}")

    print("\nConcluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
