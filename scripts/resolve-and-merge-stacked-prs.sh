#!/usr/bin/env bash
# Stacked PR Resolution & Merge Script
# Usage: bash scripts/resolve-and-merge-stacked-prs.sh [--dry-run]
set -euo pipefail

REPO="intel-agency/workflow-orchestration-service"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true && echo "=== DRY RUN MODE ==="

run_cmd() {
    if $DRY_RUN; then echo "[DRY-RUN] $*"; else echo "[EXEC] $*"; "$@"; fi
}

BASE_BRANCH="feature/standalone-orchestration-service-migration"

echo "Rebasing story branches onto ${BASE_BRANCH}..."
for branch in issues/1-project-structure issues/4-models-and-schemas issues/3-shell-bridge-dispatcher issues/2-fastapi-scaffolding issues/5-testing-framework; do
    echo "--- $branch ---"
    run_cmd git checkout "$branch"
    if ! run_cmd git rebase "$BASE_BRANCH"; then
        echo "CONFLICT on $branch - stopping"
        run_cmd git rebase --abort
        run_cmd git checkout "$BASE_BRANCH"
        exit 1
    fi
    run_cmd git push --force-with-lease origin "$branch"
    run_cmd git checkout "$BASE_BRANCH"
done

echo "Merging PRs..."
for pr in 5 8 7 6 9; do
    mergeable=$(gh pr view "$pr" --repo "$REPO" --json mergeable --jq '.mergeable')
    echo "PR #$pr mergeable: $mergeable"
    if [[ "$mergeable" == "CONFLICTING" ]]; then
        echo "CONFLICT on PR #$pr - stopping"
        exit 1
    fi
    run_cmd gh pr merge "$pr" --repo "$REPO" --squash --delete-branch
    sleep 3
done

echo "Merging PR #2 into main..."
run_cmd gh pr merge 2 --repo "$REPO" --squash
echo "Done!"
