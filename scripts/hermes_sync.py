#!/usr/bin/env python3
"""Local Hermes upstream sync helper (Cesto Agent).

Designed for a repo that is NOT a GitHub fork of NousResearch/hermes-agent
(we added the upstream remote manually). Because there is no shared git
history, `git merge`/`rebase` produce add/add conflicts on every file.

Strategy: selective `git checkout upstream/main -- <file>` for files we do
NOT own. Our protected files are left untouched, so our Ana/session/custom
surface is preserved while the core tracks upstream.

State persisted in UPSTREAM_SYNC (commit hash of last synced upstream tip).

Usage:
    python3 scripts/hermes_sync.py check   # analyze only, no changes
    python3 scripts/hermes_sync.py sync    # pull upstream into non-protected files

Exit codes:
    0  up to date, or sync succeeded
    1  errors during sync (some files failed)
    2  git/network error
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE_FILE = REPO / "UPSTREAM_SYNC"

REMOTE = "upstream"
BRANCH = "main"
UPSTREAM_REF = f"{REMOTE}/{BRANCH}"

# Files we OWN. Never overwritten by sync. Upstream edits here => warning only.
PROTECTED = (
    "enterprise/",
    "skills/cesto-damore/",
    "enterprise/mcp/ana_sessions.py",
    "hermes_cli/ana_dashboard.py",
    "web/src/App.tsx",
    "web/src/pages/AnaSessionsPage.tsx",
)

# Anchor: the release tag this repo was cut from.
BASE_TAG = "v2026.7.7.2"


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, check=check
    )


def _latest_upstream_tag() -> str | None:
    r = _run(["git", "tag", "--sort=-creatordate"], check=False)
    if r.returncode != 0:
        return None
    for t in r.stdout.splitlines():
        t = t.strip()
        if t.startswith("v") and t[1:].replace(".", "").isdigit():
            return t
    return None


def _read_state() -> str:
    if STATE_FILE.exists():
        return STATE_FILE.read_text().strip()
    return ""


def _write_state(ref: str) -> None:
    STATE_FILE.write_text(ref + "\n")


def _protected_pattern() -> str:
    return "^(?:" + "|".join(re.escape(p) for p in PROTECTED) + ")"


def _changed_files(base: str) -> list[str]:
    r = _run(
        ["git", "diff", "--name-only", f"{base}..{UPSTREAM_REF}"], check=False
    )
    if r.returncode != 0:
        return []
    return [l for l in r.stdout.splitlines() if l.strip()]


def check() -> int:
    print("==> Fetching upstream...")
    if _run(["git", "fetch", REMOTE, BRANCH, "--tags"], check=False).returncode != 0:
        print("✗ fetch failed", file=sys.stderr)
        return 2

    latest = _latest_upstream_tag()
    if latest is None:
        print("✗ no upstream tags found", file=sys.stderr)
        return 2

    base = _read_state() or BASE_TAG
    print(f"==> Upstream tip {UPSTREAM_REF} (base: {base})")

    changed = _changed_files(base)
    if not changed:
        print("✓ No upstream file changes since base. Already up to date.")
        _write_state(_run(["git", "rev-parse", UPSTREAM_REF]).stdout.strip())
        return 0

    pat = re.compile(_protected_pattern())
    protected_hits = [f for f in changed if pat.match(f)]
    free = [f for f in changed if not pat.match(f)]

    print(f"✓ {len(changed)} upstream file(s) changed "
          f"({len(free)} updatable, {len(protected_hits)} protected).")
    if protected_hits:
        print("⚠ Upstream also touched PROTECTED files (left untouched):",
              file=sys.stderr)
        for f in protected_hits:
            print(f"   - {f}", file=sys.stderr)
        print("  Review manually — your version is kept.", file=sys.stderr)
    print(f"   Run sync to pull the {len(free)} updatable file(s).")
    return 0


def sync() -> int:
    print("==> Fetching upstream...")
    if _run(["git", "fetch", REMOTE, BRANCH, "--tags"], check=False).returncode != 0:
        print("✗ fetch failed", file=sys.stderr)
        return 2

    base = _read_state() or BASE_TAG
    changed = _changed_files(base)
    if not changed:
        print("✓ Already up to date.")
        _write_state(_run(["git", "rev-parse", UPSTREAM_REF]).stdout.strip())
        return 0

    pat = re.compile(_protected_pattern())
    free = [f for f in changed if not pat.match(f)]
    protected_hits = [f for f in changed if pat.match(f)]

    if not free:
        print("✓ Only protected files changed upstream; nothing to pull.")
        _write_state(_run(["git", "rev-parse", UPSTREAM_REF]).stdout.strip())
        return 0

    print(f"==> Pulling {len(free)} upstream file(s) (protected kept)...")
    pulled = 0
    removed = 0
    skipped = 0
    for f in free:
        # Exists in upstream tip? -> checkout. Deleted upstream? -> rm here.
        has = _run(["git", "cat-file", "-e", f"{UPSTREAM_REF}:{f}"], check=False)
        if has.returncode == 0:
            r = _run(["git", "checkout", UPSTREAM_REF, "--", f], check=False)
            if r.returncode == 0:
                pulled += 1
            else:
                skipped += 1
                print(f"   ! checkout failed: {f}", file=sys.stderr)
        else:
            # Upstream removed this file; mirror the deletion.
            rr = _run(["git", "rm", "-f", "--ignore-unmatch", f], check=False)
            if rr.returncode == 0 and rr.stdout.strip():
                removed += 1
            else:
                skipped += 1

    if protected_hits:
        print(f"⚠ {len(protected_hits)} protected file(s) left as-is "
              f"(upstream changed them, yours kept).", file=sys.stderr)

    _write_state(_run(["git", "rev-parse", UPSTREAM_REF]).stdout.strip())
    print(f"✓ Synced: {pulled} pulled, {removed} removed, {skipped} skipped.")
    print("   Review diff, then commit/push when ready.")
    return 0 if skipped == 0 else 1


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "sync"):
        print(__doc__)
        return 2
    if sys.argv[1] == "check":
        return check()
    return sync()


if __name__ == "__main__":
    sys.exit(main())
