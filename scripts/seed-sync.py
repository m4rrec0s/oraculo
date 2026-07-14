#!/usr/bin/env python3
"""
Seed granular para skills e persona no Hermes Enterprise.

Este script implementa seed granular por arquivo com detecção de edições
manuais usando hash SHA256 e um manifest JSON (.seed-manifest.json).

Lógica:
1. Arquivo existe no template mas NÃO existe no volume → copiar (seed normal)
2. Arquivo existe no volume e NÃO foi editado desde o último seed → atualizar se template mudou
3. Arquivo existe no volume e FOI editado manualmente (diverge do hash do último seed) → NÃO sobrescrever

Manifest JSON (persistido no volume):
{
  "arquivo/relativo.md": {
    "seeded_hash": "sha256-abc123...",
    "seeded_at": "2026-07-13T00:00:00Z",
    "template_version": "<git-sha-ou-tag-da-imagem>"
  }
}
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_NAME = ".seed-manifest.json"


def compute_sha256(filepath: Path) -> str:
    """Computa hash SHA256 de um arquivo."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def load_manifest(profile_home: Path) -> dict[str, Any]:
    """Carrega o manifest do seed ou retorna dict vazio."""
    manifest_path = profile_home / MANIFEST_NAME
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] Manifest corrompido ou ilegível: {e}", file=sys.stderr)
            return {}
    return {}


def save_manifest(profile_home: Path, manifest: dict[str, Any]) -> None:
    """Salva o manifest no volume."""
    manifest_path = profile_home / MANIFEST_NAME
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def get_template_version() -> str:
    """Obtém a versão do template (git SHA ou 'unknown')."""
    repo_root = Path(__file__).resolve().parent.parent
    git_sha_file = repo_root / ".git" / "refs" / "heads" / "main"
    if git_sha_file.exists():
        try:
            return git_sha_file.read_text(encoding="utf-8").strip()[:8]
        except OSError:
            pass
    return "unknown"


def sync_seed(
    template_dir: Path,
    profile_home: Path,
    profile: str,
    manifest: dict[str, Any],
) -> list[str]:
    """
    Sincroniza arquivos do template para o volume com seed granular.

    Mapas de seed:
    - enterprise/soul/<profile>.md  →  <profile_home>/SOUL.md
    - enterprise/skills/<profile>/**  →  <profile_home>/skills/**

    Retorna lista de avisos de divergência (arquivos que NÃO foram sobrescritos).
    """
    warnings = []
    template_version = get_template_version()
    template_base = template_dir.resolve()
    profile_base = profile_home.resolve()

    # Garante que profile_home existe
    profile_home.mkdir(parents=True, exist_ok=True)

    # Lista de (src_file, dest_file, manifest_key, is_soul)
    # Cada tuple descreve uma cópia a fazer.
    files_to_sync: list[tuple[Path, Path, str, bool]] = []

    # 1. Persona: soul/<profile>.md → SOUL.md na raiz do profile
    soul_src = template_base / "soul" / f"{profile}.md"
    if soul_src.exists():
        soul_dest = profile_base / "SOUL.md"
        files_to_sync.append((soul_src, soul_dest, "SOUL.md", True))

    # 2. Skills do profile: skills/<profile>/** → skills/** no volume
    profile_skills_src = template_base / "skills" / profile
    if profile_skills_src.exists():
        for src_file in profile_skills_src.rglob("*"):
            if src_file.is_dir():
                continue
            rel_to_skills = src_file.relative_to(profile_skills_src)
            dest_file = profile_base / "skills" / rel_to_skills
            manifest_key = "skills/" + str(rel_to_skills)
            files_to_sync.append((src_file, dest_file, manifest_key, False))

    for src_file, dest_file, manifest_key, is_soul in files_to_sync:
        # Garante diretório pai
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Caso 1: arquivo não existe no volume → copiar
        if not dest_file.exists():
            dest_file.write_bytes(src_file.read_bytes())
            file_hash = compute_sha256(dest_file)
            manifest[manifest_key] = {
                "seeded_hash": file_hash,
                "seeded_at": datetime.now(timezone.utc).isoformat(),
                "template_version": template_version,
            }
            print(f"[SEED] Copiado: {manifest_key}")
            continue

        # Caso 2+: arquivo existe no volume
        current_hash = compute_sha256(dest_file)

        if manifest_key not in manifest:
            # Arquivo pré-existente antes desta migração → adotar sem sobrescrever
            manifest[manifest_key] = {
                "seeded_hash": current_hash,
                "seeded_at": datetime.now(timezone.utc).isoformat(),
                "template_version": "migrated",
            }
            if is_soul:
                print(f"[SEED] SOUL.md pré-existente adotado (migração) — NÃO sobrescrito.")
            else:
                print(f"[SEED] Arquivo pré-existente detectado (migração): {manifest_key}")
            continue

        # Arquivo já estava no manifest
        prev_hash = manifest[manifest_key].get("seeded_hash")
        template_hash = compute_sha256(src_file)

        if current_hash == prev_hash == template_hash:
            # Nada mudou → já está sincronizado
            continue

        if current_hash == prev_hash and prev_hash != template_hash:
            # Não foi editado desde o seed, mas template mudou → atualizar
            dest_file.write_bytes(src_file.read_bytes())
            manifest[manifest_key]["seeded_hash"] = template_hash
            manifest[manifest_key]["seeded_at"] = datetime.now(timezone.utc).isoformat()
            manifest[manifest_key]["template_version"] = template_version
            print(f"[SEED] Atualizado (template mudou): {manifest_key}")
            continue

        if current_hash != prev_hash:
            # Foi editado manualmente → NÃO sobrescrever, avisar
            if is_soul:
                warnings.append(
                    f"[SOUL-DIVERGENCE] SOUL.md foi editado manualmente. "
                    f"A edição local NÃO será sobrescrita para preservar sua customização. "
                    f"Hash local: {current_hash[:12]}... | Hash template: {template_hash[:12]}..."
                )
            else:
                warnings.append(
                    f"[DIVERGENCE] {manifest_key} foi editado manualmente. "
                    f"A edição local NÃO será sobrescrita. "
                    f"Hash local: {current_hash[:12]}... | Hash template: {template_hash[:12]}..."
                )

    return warnings


def main() -> int:
    """Função principal do seed-sync."""
    # Argumentos: template_dir profile_home profile
    if len(sys.argv) != 4:
        print(f"Uso: {sys.argv[0]} <template_dir> <profile_home> <profile>", file=sys.stderr)
        return 1

    template_dir = Path(sys.argv[1])
    profile_home = Path(sys.argv[2])
    profile = sys.argv[3]

    if not template_dir.is_dir():
        print(f"[ERROR] Diretório de template não encontrado: {template_dir}", file=sys.stderr)
        return 1

    # Carrega ou cria manifest
    manifest = load_manifest(profile_home)

    # Executa sync
    warnings = sync_seed(template_dir, profile_home, profile, manifest)

    # Salva manifest (se houver mudanças)
    save_manifest(profile_home, manifest)

    # Imprime avisos (se houver)
    if warnings:
        print("\n[WARNINGS] Arquivos com divergência detectada:", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
        print(file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
