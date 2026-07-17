#!/usr/bin/env python3
"""Local Hermes upstream sync helper (Cesto Agent).

Compares the local fork against NousResearch/hermes-agent, detects collisions
against Cesto's protected files, and optionally merges upstream when safe.

State is persisted in UPSTREAM_SYNC (the last upstream tag we synced to).

Usage:
    python3 scripts/hermes_sync.py check   # analyze only, no changes
    python3 scripts/hermes_sync.py sync    # merge upstream/main if no collision

Exit codes:
    0  up to date, or sync succeeded (no collision)
    1  collision detected (sync aborted)
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

# Files we OWN. Upstream edits here => collision, sync aborts for manual review.
PROTECTED = (
    "enterprise/",
    "skills/cesto-damore/",
    "enterprise/mcp/ana_sessions.py",
    "hermes_cli/ana_dashboard.py",
    "web/src/App.tsx",
    "web/src/pages/AnaSessionsPage.tsx",
)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True,
        check=check,
    )


def _latest_upstream_tag() -> str | None:
    """Newest semver-ish tag on upstream (e.g. v2026.7.7.2)."""
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


def _write_state(tag: str) -> None:
    STATE_FILE.write_text(tag + "\n")


def _protected_pattern() -> str:
    return "^(?:" + "|".join(PROTECTED) + ")"


def _same_commit(a: str, b: str) -> bool:
    """True if git refs a and b point at the same commit."""
    ra = _run(["git", "rev-parse", a], check=False)
    rb = _run(["git", "rev-parse", b], check=False)
    return ra.returncode == 0 and rb.returncode == 0 and ra.stdout.strip() == rb.stdout.strip()


def check() -> int:
    print("==> Fetching upstream...")
    if _run(["git", "fetch", REMOTE, BRANCH, "--tags"], check=False).returncode != 0:
        print("✗ fetch failed", file=sys.stderr)
        return 2

    latest = _latest_upstream_tag()
    if latest is None:
        print("✗ no upstream tags found", file=sys.stderr)
        return 2

    base = _read_state()
    target = UPSTREAM_REF

    # First run (no state): anchor on the release tag this fork was cut from,
    # not HEAD — the fork diverged from upstream so HEAD..upstream is huge.
    if not base:
        base = latest
        print(f"==> No sync state; anchoring on release tag {latest}")

    if base == target or _same_commit(base, target):
        print(f"✓ Already synced to upstream tip ({target}). Nothing to do.")
        _write_state(_run(["git", "rev-parse", target]).stdout.strip())
        return 0

    print(f"==> Upstream tip {target} (synced base: {base})")

    # Files upstream changed since the base tag.
    merge_base = base
    r = _run(["git", "diff", "--name-only", f"{merge_base}..{UPSTREAM_REF}"], check=False)
    if r.returncode != 0:
        print(f"✗ diff failed (base {merge_base} may be invalid)", file=sys.stderr)
        return 2

    changed = [l for l in r.stdout.splitlines() if l.strip()]
    if not changed:
        print(f"✓ Upstream has no file changes vs {merge_base}.")
        _write_state(_run(["git", "rev-parse", target]).stdout.strip())
        return 0

    pat = re.compile(_protected_pattern())
    collide = [f for f in changed if pat.match(f)]

    if collide:
        print("⚠ COLLISION — upstream modified protected files:", file=sys.stderr)
        for f in collide:
            print(f"   - {f}", file=sys.stderr)
        print("✗ Sync aborted. Review manually.", file=sys.stderr)
        return 1

    print(f"✓ No collision. {len(changed)} upstream file(s) changed, "
          f"none in protected set.")
    print(f"   Ready to sync to {target}. Run: python3 scripts/hermes_sync.py sync")
    return 0


def sync() -> int:
    rc = check()
    if rc != 0:
        return rc

    latest = _latest_upstream_tag()
    print(f"==> Merging {UPSTREAM_REF}...")
    r = _run(["git", "merge", UPSTREAM_REF, "--no-edit"], check=False)
    if r.returncode != 0:
        print("✗ Merge failed (conflicts?). Aborting.", file=sys.stderr)
        print(r.stdout, file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        return 1

    _write_state(_run(["git", "rev-parse", UPSTREAM_REF]).stdout.strip())
    print(f"✓ Synced to {latest}. Review the diff, then push & deploy when ready.")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("check", "sync"):
        print(__doc__)
        return 2
    if sys.argv[1] == "check":
        return check()
    return sync()


if __name__ == "__main__":
    sys.exit(main())
