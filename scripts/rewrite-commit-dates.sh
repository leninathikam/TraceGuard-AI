#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export FILTER_BRANCH_SQUELCH_WARNING=1
git rebase --root --exec 'D=$(date "+%Y-%m-%d %H:%M:%S %z"); export GIT_COMMITTER_DATE="$D"; git commit --amend --no-edit --date="$D"'
git log --format='%h %ai %ci %s' -5
