#!/usr/bin/env bash
#
# sync_upstream.sh — SCAN-ONLY upstream collision checker.
# Does NOT apply any changes. Exits non-zero on collision so CI can block.
#
# Usage: scripts/sync_upstream.sh [upstream_remote] [upstream_branch]
#   default: upstream / main
#
# Exit codes:
#   0  = no collision, safe to proceed (manual/CI cherry-pick still your call)
#   1  = collision detected in protected files
#   2  = git/network error (fetch failed, no merge-base, etc.)
#
set -euo pipefail

REMOTE="${1:-upstream}"
BRANCH="${2:-main}"
UPSTREAM_REF="${REMOTE}/${BRANCH}"

# Anchor: our fork was cut from this upstream release tag. Upstream history
# is unrelated to our local commits (divergent fork), so merge-base fails.
# Use the tag as the baseline for "what upstream changed since our version".
BASE_TAG="${BASE_TAG:-v2026.7.7.2}"

# Files we OWN and must never let upstream silently overwrite via blind merge.
# Anything here touched by upstream since our fork-point => collision.
PROTECTED=(
  "enterprise/"
  "skills/cesto-damore/"
  "enterprise/mcp/ana_sessions.py"
  "hermes_cli/ana_dashboard.py"
  "web/src/App.tsx"
  "web/src/pages/AnaSessionsPage.tsx"
)

echo "==> Fetching ${UPSTREAM_REF}..."
if ! git fetch "${REMOTE}" "${BRANCH}" --quiet; then
  echo "✗ fetch failed" >&2
  exit 2
fi

MERGE_BASE="$(git merge-base HEAD "${UPSTREAM_REF}" 2>/dev/null || true)"
if [ -z "${MERGE_BASE}" ]; then
  # Divergent fork: fall back to the release tag anchor.
  if git rev-parse "${BASE_TAG}" >/dev/null 2>&1; then
    MERGE_BASE="${BASE_TAG}"
    echo "==> No merge-base; using tag anchor ${BASE_TAG}"
  else
    echo "✗ no merge-base and tag ${BASE_TAG} missing (git fetch --tags?)" >&2
    exit 2
  fi
fi

echo "==> Diffing upstream files since fork-point ${MERGE_BASE:0:10}..."
mapfile -t UPS_FILES < <(git diff --name-only "${MERGE_BASE}".."${UPSTREAM_REF}")

if [ "${#UPS_FILES[@]}" -eq 0 ]; then
  echo "✓ Upstream has no new commits since fork-point."
  exit 0
fi

# Build pattern for grep -E from protected prefixes
PATTERN="$(printf '^%s' "${PROTECTED[0]}"; printf '|^%s' "${PROTECTED[@]:1}")"

COLLIDE=()
for f in "${UPS_FILES[@]}"; do
  if printf '%s\n' "$f" | grep -Eq "$PATTERN"; then
    COLLIDE+=("$f")
  fi
done

if [ "${#COLLIDE[@]}" -gt 0 ]; then
  echo "⚠ COLLISION: upstream modified files you protect:" >&2
  for f in "${COLLIDE[@]}"; do
    echo "   - $f" >&2
  done
  echo "==> Upstream commits touching protected files:" >&2
  git log --oneline "${MERGE_BASE}".."${UPSTREAM_REF}" -- "${COLLIDE[@]}" >&2
  echo "✗ Blocking. Review manually before merging upstream." >&2
  exit 1
fi

echo "✓ No collision. ${#UPS_FILES[@]} upstream file(s) changed, none in protected set."
echo "   Safe to cherry-pick / merge at your discretion."
exit 0
