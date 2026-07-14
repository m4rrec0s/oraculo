"""
EditService — Service de edição runtime de persona e skills.

Responsabilidades:
- Ler e escrever SOUL.md (persona) e skills de um profile.
- Atualizar .seed-manifest.json após cada edição para que seed-sync.py
  não marque a edição como "divergência manual".
- Criar backup em .edit-history/<arquivo>/<timestamp>.md antes de sobrescrever.
- Retornar EditResult com informações da operação.

Esta camada não depende de terminal ($EDITOR) — isso fica na CLI.
Pode ser chamada tanto da CLI quanto de um handler HTTP futuro.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Tipos de resultado
# ---------------------------------------------------------------------------

@dataclass
class EditResult:
    success: bool
    message: str
    backup_path: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reload_triggered: bool = False
    changed: bool = True


# ---------------------------------------------------------------------------
# Helpers de hash/manifest (compartilhados com seed-sync.py)
# ---------------------------------------------------------------------------

MANIFEST_NAME = ".seed-manifest.json"
EDIT_HISTORY_DIR = ".edit-history"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(profile_home: Path) -> dict[str, Any]:
    manifest_path = profile_home / MANIFEST_NAME
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_manifest(profile_home: Path, manifest: dict[str, Any]) -> None:
    (profile_home / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _update_manifest_entry(profile_home: Path, manifest_key: str, file_path: Path) -> None:
    """Atualiza a entrada do manifest após uma edição legítima via service."""
    manifest = _load_manifest(profile_home)
    manifest[manifest_key] = {
        "seeded_hash": _sha256(file_path),
        "seeded_at": datetime.now(timezone.utc).isoformat(),
        "template_version": manifest.get(manifest_key, {}).get("template_version", "operator-edit"),
    }
    _save_manifest(profile_home, manifest)


def _make_backup(file_path: Path, profile_home: Path, manifest_key: str) -> str:
    """Cria backup do arquivo em .edit-history/<manifest_key>/<timestamp>.md.

    Retorna o path do backup criado.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = profile_home / EDIT_HISTORY_DIR / manifest_key
    backup_dir.mkdir(parents=True, exist_ok=True)
    suffix = file_path.suffix or ".md"
    backup_path = backup_dir / f"{ts}{suffix}"
    backup_path.write_bytes(file_path.read_bytes())
    return str(backup_path)


# ---------------------------------------------------------------------------
# Resolução de paths
# ---------------------------------------------------------------------------

def _resolve_profile_home(profile: str) -> Path:
    """Resolve HERMES_HOME do profile.

    Prioridade:
    1. HERMES_<PROFILE>_HOME (ex: HERMES_ATENDIMENTO_HOME)
    2. HERMES_HOME/profiles/<profile> se HERMES_HOME setado
    3. ~/.hermes/profiles/<profile> como fallback
    """
    env_key = f"HERMES_{profile.upper()}_HOME"
    if val := os.environ.get(env_key):
        return Path(val).expanduser()
    hermes_home = os.environ.get("HERMES_HOME", "")
    if hermes_home:
        base = Path(hermes_home)
        # Se HERMES_HOME já aponta para o profile (ex: .hermes/profiles/atendimento)
        if base.name == profile:
            return base
        return base / "profiles" / profile
    return Path.home() / ".hermes" / "profiles" / profile


def _soul_path(profile_home: Path) -> Path:
    return profile_home / "SOUL.md"


def _skill_path(profile_home: Path, skill_name: str) -> Path:
    return profile_home / "skills" / skill_name / "SKILL.md"


# ---------------------------------------------------------------------------
# Validações
# ---------------------------------------------------------------------------

def _validate_soul(content: str) -> str | None:
    """Retorna mensagem de erro ou None se válido."""
    stripped = content.strip()
    if not stripped:
        return "SOUL.md não pode estar vazio."
    # Exige pelo menos um heading (#) — estrutura mínima
    if not any(line.startswith("#") for line in stripped.splitlines()):
        return "SOUL.md deve conter ao menos um heading (linha começando com #)."
    return None


def _validate_skill(content: str) -> str | None:
    """Retorna mensagem de erro ou None se válido."""
    stripped = content.strip()
    if not stripped:
        return "SKILL.md não pode estar vazio."
    # Frontmatter YAML obrigatório (--- ... ---)
    lines = stripped.splitlines()
    if not (lines[0].strip() == "---"):
        return "SKILL.md deve começar com frontmatter YAML (linha '---')."
    return None


# ---------------------------------------------------------------------------
# EditService
# ---------------------------------------------------------------------------

class EditService:
    """Service de edição runtime de persona e skills de um profile."""

    def __init__(self, profile: str, profile_home: Path | None = None) -> None:
        self.profile = profile
        self.profile_home = profile_home or _resolve_profile_home(profile)

    # -- Leitura --

    def get_persona(self) -> tuple[str, None] | tuple[None, str]:
        """Retorna (content, None) ou (None, error_message)."""
        path = _soul_path(self.profile_home)
        if not path.exists():
            return None, f"SOUL.md não encontrado em {path}"
        return path.read_text(encoding="utf-8"), None

    def get_skill(self, skill_name: str) -> tuple[str, None] | tuple[None, str]:
        """Retorna (content, None) ou (None, error_message)."""
        path = _skill_path(self.profile_home, skill_name)
        if not path.exists():
            return None, f"Skill '{skill_name}' não encontrada em {path}"
        return path.read_text(encoding="utf-8"), None

    def list_skills(self) -> list[str]:
        """Lista nomes de skills disponíveis no profile."""
        skills_dir = self.profile_home / "skills"
        if not skills_dir.exists():
            return []
        return sorted(
            d.name
            for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        )

    # -- Edição --

    def edit_persona(self, new_content: str, trigger_reload: bool = True) -> EditResult:
        """Edita a persona (SOUL.md) do profile.

        Passos:
        1. Valida conteúdo.
        2. Compara hash — se não mudou, retorna sem escrever.
        3. Cria backup.
        4. Escreve novo conteúdo.
        5. Atualiza manifest.
        6. Dispara reload se solicitado.
        """
        path = _soul_path(self.profile_home)
        manifest_key = "SOUL.md"

        # Validação
        if err := _validate_soul(new_content):
            return EditResult(success=False, message=err, changed=False)

        # Idempotência: sem mudança real → não escreve
        if path.exists() and _sha256(path) == hashlib.sha256(new_content.encode()).hexdigest():
            return EditResult(
                success=True,
                message="Sem alterações (conteúdo idêntico).",
                changed=False,
            )

        # Backup
        backup_path = None
        if path.exists():
            backup_path = _make_backup(path, self.profile_home, manifest_key)

        # Escreve
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")

        # Atualiza manifest
        _update_manifest_entry(self.profile_home, manifest_key, path)

        # Reload
        reloaded = False
        if trigger_reload:
            reloaded = _trigger_gateway_reload(self.profile)

        _log_edit(self.profile_home, manifest_key)

        return EditResult(
            success=True,
            message=f"Persona do profile '{self.profile}' atualizada com sucesso.",
            backup_path=backup_path,
            reload_triggered=reloaded,
        )

    def edit_skill(
        self, skill_name: str, new_content: str, trigger_reload: bool = True
    ) -> EditResult:
        """Edita uma skill existente do profile.

        Não cria skills novas — apenas edita as que já existem no volume.
        """
        path = _skill_path(self.profile_home, skill_name)
        manifest_key = f"skills/{skill_name}/SKILL.md"

        if not path.exists():
            return EditResult(
                success=False,
                message=f"Skill '{skill_name}' não encontrada. Use 'skill list' para ver skills disponíveis.",
                changed=False,
            )

        # Validação
        if err := _validate_skill(new_content):
            return EditResult(success=False, message=err, changed=False)

        # Idempotência
        if _sha256(path) == hashlib.sha256(new_content.encode()).hexdigest():
            return EditResult(
                success=True,
                message="Sem alterações (conteúdo idêntico).",
                changed=False,
            )

        # Backup
        backup_path = _make_backup(path, self.profile_home, manifest_key)

        # Escreve
        path.write_text(new_content, encoding="utf-8")

        # Atualiza manifest
        _update_manifest_entry(self.profile_home, manifest_key, path)

        # Reload
        reloaded = False
        if trigger_reload:
            reloaded = _trigger_gateway_reload(self.profile)

        _log_edit(self.profile_home, manifest_key)

        return EditResult(
            success=True,
            message=f"Skill '{skill_name}' do profile '{self.profile}' atualizada com sucesso.",
            backup_path=backup_path,
            reload_triggered=reloaded,
        )


# ---------------------------------------------------------------------------
# Reload do gateway
# ---------------------------------------------------------------------------

def _trigger_gateway_reload(profile: str) -> bool:
    """Dispara reload do gateway sem restart de container.

    Estratégia: SIGHUP no processo do gateway do profile.

    O gateway do Hermes, ao receber SIGHUP, encerra o loop de aceitação de
    novas sessões, aguarda as sessões em andamento finalizarem, e relê
    configuração/skills para novos ciclos de conversa. Sessões já abertas
    NÃO são interrompidas.

    Se SIGHUP não for suficiente ou o processo não for encontrado,
    retorna False (falha não-fatal — a mudança já foi salva no volume
    e valerá no próximo restart natural do container).
    """
    pid = _find_gateway_pid(profile)
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGHUP)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _find_gateway_pid(profile: str) -> int | None:
    """Encontra o PID do processo gateway do profile.

    Busca por processos que contenham 'gateway run' e o profile na linha de
    comando. Usa /proc no Linux ou pgrep como fallback.
    """
    # Tenta via /proc (Linux — disponível nos containers)
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            cmdline_file = pid_dir / "cmdline"
            if not cmdline_file.exists():
                continue
            try:
                cmdline = cmdline_file.read_bytes().replace(b"\x00", b" ").decode(errors="replace")
                if "gateway" in cmdline and "run" in cmdline and profile in cmdline:
                    return int(pid_dir.name)
            except (OSError, ValueError):
                continue
    except OSError:
        pass

    # Fallback: pgrep
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"gateway.*run.*{profile}"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            pids = result.stdout.strip().splitlines()
            if pids:
                return int(pids[0])
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    return None


# ---------------------------------------------------------------------------
# Log de edição
# ---------------------------------------------------------------------------

def _log_edit(profile_home: Path, manifest_key: str) -> None:
    """Registra edição em stdout e em .edit-history/edits.log."""
    ts = datetime.now(timezone.utc).isoformat()
    msg = f"[EDIT] {ts} — {manifest_key}"
    print(msg)
    log_path = profile_home / EDIT_HISTORY_DIR / "edits.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
