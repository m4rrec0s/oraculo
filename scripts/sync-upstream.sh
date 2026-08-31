#!/bin/bash
# =============================================================================
# sync-upstream.sh — Automated upstream sync for Oraculo fork
#
# Usage:
#   ./scripts/sync-upstream.sh                    # sync to latest upstream tag
#   ./scripts/sync-upstream.sh v2026.8.27         # sync to specific tag
#   ./scripts/sync-upstream.sh --dry-run          # preview without changes
#   ./scripts/sync-upstream.sh --abort            # abort ongoing merge
#   ./scripts/sync-upstream.sh --continue         # continue after conflict resolution
#
# What it does:
#   1. Fetches upstream (NousResearch/hermes-agent)
#   2. Detects target tag (latest or specified)
#   3. Creates merge branch
#   4. Attempts merge with conflict resolution
#   5. Auto-resolves: upstream files → accept theirs, enterprise/ → keep ours
#   6. Runs tests
#   7. Builds Docker image
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[SYNC]${NC} $*"; }
ok()   { echo -e "${GREEN}[SYNC]${NC} $*"; }
warn() { echo -e "${YELLOW}[SYNC]${NC} $*"; }
err()  { echo -e "${RED}[SYNC]${NC} $*" >&2; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Our custom files/dirs that should NEVER be overwritten by upstream
OUR_FILES=(
    "enterprise/"
    "docker-compose.dev.yml"
    "docker-compose.easypanel.yml"
    "Dockerfile.enterprise"
    "docker/enterprise-entrypoint.sh"
    "scripts/seed-sync.py"
    "scripts/seed-sync.sh"
    "scripts/hermes_sync.py"
    "hermes_cli/ana_dashboard.py"
    "web/src/pages/AtendimentoPage.tsx"
    "skills/cesto-damore/"
    "UPSTREAM_SYNC"
    "EASYPANEL_AUTODEPLOY.md"
    "README.EASYPANEL.md"
)

# Core files where we have small patches — these need manual review on conflict
PATCHED_FILES=(
    "gateway/platforms/api_server.py"
    "hermes_cli/profiles.py"
    "hermes_cli/web_server.py"
    "Dockerfile"
)

# ── Parse args ──────────────────────────────────────────────────────────────
DRY_RUN=false
ABORT=false
CONTINUE=false
TARGET_TAG=""

for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=true ;;
        --abort)    ABORT=true ;;
        --continue) CONTINUE=true ;;
        --help|-h)
            echo "Usage: $0 [--dry-run|--abort|--continue] [TARGET_TAG]"
            exit 0
            ;;
        *) TARGET_TAG="$arg" ;;
    esac
done

# ── Handle --abort ──────────────────────────────────────────────────────────
if $ABORT; then
    log "Aborting merge..."
    git merge --abort 2>/dev/null || true
    ok "Merge aborted."
    exit 0
fi

# ── Handle --continue ───────────────────────────────────────────────────────
if $CONTINUE; then
    log "Continuing merge after conflict resolution..."
    git add -A
    git commit --no-edit
    ok "Merge committed."
    echo ""
    log "Next steps:"
    echo "  1. Run tests:   scripts/run_tests.sh -q --tb=short"
    echo "  2. Build Docker: docker build -t hermes-enterprise:local -f Dockerfile ."
    echo "  3. Push:         git push origin main"
    exit 0
fi

# ── Step 1: Fetch upstream ─────────────────────────────────────────────────
log "Fetching upstream..."
if ! git remote get-url upstream >/dev/null 2>&1; then
    err "No 'upstream' remote configured."
    echo "  Add it: git remote add upstream https://github.com/NousResearch/hermes-agent.git"
    exit 1
fi

git fetch upstream --tags 2>&1 | tail -3
ok "Upstream fetched."

# ── Step 2: Determine target tag ───────────────────────────────────────────
if [[ -z "$TARGET_TAG" ]]; then
    # Get latest semver tag
    TARGET_TAG=$(git tag -l "v2026*" | sort -V | tail -1)
    if [[ -z "$TARGET_TAG" ]]; then
        err "No v2026* tags found in upstream."
        exit 1
    fi
fi

# Verify tag exists
if ! git rev-parse "$TARGET_TAG" >/dev/null 2>&1; then
    err "Tag/commit '$TARGET_TAG' not found upstream."
    echo "  Available tags:"
    git tag -l "v2026*" | sort -V | tail -10
    exit 1
fi

CURRENT_VERSION=$(git log --oneline -1 HEAD | sed 's/^[a-f0-9]* //')
TARGET_SHA=$(git rev-parse --short "$TARGET_TAG")
log "Current:  $CURRENT_VERSION"
log "Target:   $TARGET_TAG ($TARGET_SHA)"

# Check if already synced
if git merge-base --is-ancestor "$TARGET_TAG" HEAD 2>/dev/null; then
    ok "Already synced to $TARGET_TAG or newer."
    exit 0
fi

# Count commits between
AHEAD=$(git rev-list --count HEAD.."$TARGET_TAG" 2>/dev/null || echo "?")
log "Commits ahead: ~$AHEAD"

if $DRY_RUN; then
    log "DRY RUN — would merge $TARGET_TAG into $(git branch --show-current)"
    log "Files that would be affected:"
    git diff --stat HEAD..."$TARGET_TAG" | tail -5
    exit 0
fi

# ── Step 3: Create merge branch ────────────────────────────────────────────
BRANCH_NAME="sync/$(date +%Y%m%d)-${TARGET_TAG}"
log "Creating branch: $BRANCH_NAME"
git checkout -b "$BRANCH_NAME" 2>/dev/null || git checkout "$BRANCH_NAME"

# ── Step 4: Merge ──────────────────────────────────────────────────────────
log "Merging $TARGET_TAG..."
MERGE_OUTPUT=$(git merge "$TARGET_TAG" --no-edit 2>&1) && MERGE_OK=true || MERGE_OK=false

if $MERGE_OK; then
    ok "Merge clean! No conflicts."
else
    warn "Merge conflicts detected."
    echo ""

    # Get list of conflicted files
    CONFLICTS=$(git diff --name-only --diff-filter=U 2>/dev/null || true)
    if [[ -z "$CONFLICTS" ]]; then
        CONFLICTS=$(git ls-files -u | awk '{print $4}' | sort -u)
    fi

    CONFLICT_COUNT=$(echo "$CONFLICTS" | grep -c "." || echo 0)
    log "Conflicting files ($CONFLICT_COUNT):"
    echo "$CONFLICTS" | while read -r f; do
        # Classify: ours-only, theirs-only, or needs review
        IS_OURS=false
        for pattern in "${OUR_FILES[@]}"; do
            if [[ "$f" == $pattern* ]]; then
                IS_OURS=true
                break
            fi
        done

        IS_PATCHED=false
        for pf in "${PATCHED_FILES[@]}"; do
            if [[ "$f" == "$pf" ]]; then
                IS_PATCHED=true
                break
            fi
        done

        if $IS_OURS; then
            echo -e "  ${GREEN}✓ OURS${NC}  $f (enterprise — will keep ours)"
        elif $IS_PATCHED; then
            echo -e "  ${YELLOW}⚠ REVIEW${NC} $f (we have patches — manual merge needed)"
        else
            echo -e "  ${BLUE}→ THEIRS${NC} $f (upstream — will accept theirs)"
        fi
    done
    echo ""

    # ── Step 5: Auto-resolve ───────────────────────────────────────────────
    log "Auto-resolving conflicts..."

    # Accept upstream for non-our files
    for f in $CONFLICTS; do
        IS_OURS=false
        for pattern in "${OUR_FILES[@]}"; do
            if [[ "$f" == $pattern* ]]; then
                IS_OURS=true
                break
            fi
        done

        IS_PATCHED=false
        for pf in "${PATCHED_FILES[@]}"; do
            if [[ "$f" == "$pf" ]]; then
                IS_PATCHED=true
                break
            fi
        done

        if $IS_OURS; then
            # Keep our version for enterprise/ files
            git checkout --ours "$f" 2>/dev/null && git add "$f"
            ok "  Kept ours: $f"
        elif $IS_PATCHED; then
            # Leave for manual resolution
            warn "  Needs manual merge: $f"
        else
            # Accept upstream version
            git checkout --theirs "$f" 2>/dev/null && git add "$f"
            ok "  Accepted upstream: $f"
        fi
    done

    # Show remaining unresolved
    REMAINING=$(git diff --name-only --diff-filter=U 2>/dev/null || true)
    if [[ -n "$REMAINING" ]]; then
        echo ""
        warn "Files needing manual resolution:"
        echo "$REMAINING" | while read -r f; do
            echo "  - $f"
        done
        echo ""
        warn "Resolve conflicts, then run:"
        echo "  git add -A && git commit --no-edit"
        echo "  # or: $0 --continue"
        echo ""
        warn "Or abort with: $0 --abort"
        exit 1
    fi

    # All auto-resolved — commit
    git add -A
    git commit --no-edit
    ok "Merge committed (auto-resolved)."
fi

# ── Step 6: Update tracking ────────────────────────────────────────────────
log "Updating UPSTREAM_SYNC..."
cat > UPSTREAM_SYNC << EOF
# Upstream sync tracking
# This file records the last synced upstream version.
# Updated automatically by scripts/sync-upstream.sh

upstream_repo: https://github.com/NousResearch/hermes-agent.git
target_tag: $TARGET_TAG
target_sha: $(git rev-parse "$TARGET_TAG" 2>/dev/null || echo "unknown")
synced_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
synced_by: sync-upstream.sh
EOF
git add UPSTREAM_SYNC
git commit --amend --no-edit 2>/dev/null || git commit -m "chore: sync upstream $TARGET_TAG" --no-edit

# ── Step 7: Summary ────────────────────────────────────────────────────────
echo ""
echo "============================================"
ok "SYNC COMPLETE → $TARGET_TAG"
echo "============================================"
echo ""
echo "Branch: $BRANCH_NAME"
echo ""
echo "Next steps:"
echo "  1. Run tests:      scripts/run_tests.sh -q --tb=short"
echo "  2. Build Docker:   docker build -t hermes-enterprise:local -f Dockerfile ."
echo "  3. Test containers: docker compose -f docker-compose.dev.yml up -d"
echo "  4. Push branch:    git push origin $BRANCH_NAME"
echo "  5. Create PR:      gh pr create --base main --head $BRANCH_NAME"
echo ""
echo "If tests pass and Docker works, merge to main:"
echo "  git checkout main && git merge $BRANCH_NAME && git push origin main"
