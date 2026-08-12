#!/usr/bin/env bash
# Prioritize merge queue entries by label.
#
# PRs labelled "ci-critical" are moved to the very top, followed by
# "ga-critical" PRs.  Within each tier the original queue order is
# preserved.  PRs that are already in the correct position are left
# untouched to avoid unnecessary queue churn.
#
# Usage:
#   tools/ci/merge-queue-prioritize.sh            # default repo/branch
#   tools/ci/merge-queue-prioritize.sh --dry-run  # show what would happen
#
# Requires: gh (GitHub CLI), jq

set -euo pipefail

OWNER="syntara-orchestration"
REPO="syntara"
BRANCH="devel"
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --help|-h)
      sed -n '2,/^$/s/^# \?//p' "$0"
      exit 0
      ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

for cmd in gh jq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: '$cmd' is required but not found." >&2
    exit 1
  fi
done

# ── Query merge queue ────────────────────────────────────────────────

QUERY='
query($owner: String!, $repo: String!, $branch: String!) {
  repository(owner: $owner, name: $repo) {
    mergeQueue(branch: $branch) {
      entries(first: 100) {
        nodes {
          id
          position
          state
          jump
          pullRequest {
            id
            number
            title
            url
            labels(first: 20) {
              nodes { name }
            }
          }
        }
      }
    }
  }
}'

echo "Querying merge queue for $OWNER/$REPO (branch: $BRANCH)..."
echo ""

RESULT=$(gh api graphql \
  -f query="$QUERY" \
  -f owner="$OWNER" \
  -f repo="$REPO" \
  -f branch="$BRANCH")

ENTRIES=$(echo "$RESULT" | jq '.data.repository.mergeQueue.entries.nodes')
TOTAL=$(echo "$ENTRIES" | jq 'length')

if [ "$TOTAL" -eq 0 ]; then
  echo "Merge queue is empty."
  exit 0
fi

echo "=== Current merge queue ($TOTAL entries) ==="
echo "$ENTRIES" | jq -r '
  .[] | "  #\(.position)  PR #\(.pullRequest.number)  [\(.state)]  \(.pullRequest.title)  (\([.pullRequest.labels.nodes[].name] | join(", ")))"'
echo ""

# ── Build desired prefix ─────────────────────────────────────────────
# ci-critical first, then ga-critical, each group keeping its current
# relative queue order (sorted by position).

CI_CRITICAL=$(echo "$ENTRIES" | jq '[.[] | select(.pullRequest.labels.nodes | map(.name) | index("ci-critical"))] | sort_by(.position)')
GA_CRITICAL=$(echo "$ENTRIES" | jq '[.[] | select(.pullRequest.labels.nodes | map(.name) | index("ga-critical")) | select(.pullRequest.labels.nodes | map(.name) | index("ci-critical") | not)] | sort_by(.position)')

CI_COUNT=$(echo "$CI_CRITICAL" | jq 'length')
GA_COUNT=$(echo "$GA_CRITICAL" | jq 'length')

echo "=== ci-critical PRs ($CI_COUNT) ==="
if [ "$CI_COUNT" -eq 0 ]; then
  echo "  (none)"
else
  echo "$CI_CRITICAL" | jq -r '.[] | "  #\(.position)  PR #\(.pullRequest.number)  \(.pullRequest.title)"'
fi

echo "=== ga-critical PRs ($GA_COUNT) ==="
if [ "$GA_COUNT" -eq 0 ]; then
  echo "  (none)"
else
  echo "$GA_CRITICAL" | jq -r '.[] | "  #\(.position)  PR #\(.pullRequest.number)  \(.pullRequest.title)"'
fi
echo ""

# Desired prefix: ci-critical entries then ga-critical entries.
DESIRED=$(echo "$CI_CRITICAL $GA_CRITICAL" | jq -s 'add // []')
DESIRED_COUNT=$(echo "$DESIRED" | jq 'length')

if [ "$DESIRED_COUNT" -eq 0 ]; then
  echo "No priority PRs found. Nothing to do."
  exit 0
fi

# ── Determine which PRs actually need jumping ────────────────────────
# Compare the desired prefix against the actual top N positions.
# Find the longest matching prefix — only PRs after the mismatch need
# to be jumped.

ACTUAL_PREFIX=$(echo "$ENTRIES" | jq --argjson n "$DESIRED_COUNT" '[.[:$n][].pullRequest.number]')
DESIRED_NUMBERS=$(echo "$DESIRED" | jq '[.[].pullRequest.number]')

ALREADY_CORRECT=$(jq -n --argjson a "$ACTUAL_PREFIX" --argjson d "$DESIRED_NUMBERS" '$a == $d')

if [ "$ALREADY_CORRECT" = "true" ]; then
  echo "Priority PRs are already at the top in the correct order. Nothing to do."
  exit 0
fi

# Find how many leading entries already match.
MATCH_LEN=$(jq -n --argjson a "$ACTUAL_PREFIX" --argjson d "$DESIRED_NUMBERS" '
  ([$a,$d] | map(length) | min) as $len |
  [range($len) | select($a[.] != $d[.])] |
  if length == 0 then $len else .[0] end')

TO_JUMP=$(echo "$DESIRED" | jq --argjson skip "$MATCH_LEN" '.[$skip:]')
JUMP_COUNT=$(echo "$TO_JUMP" | jq 'length')

echo "$MATCH_LEN of $DESIRED_COUNT priority PR(s) already in place."
echo "$JUMP_COUNT PR(s) need to be moved."
echo ""

if [ "$DRY_RUN" = true ]; then
  echo "[dry-run] Would jump the following PRs (in reverse order):"
  echo "$TO_JUMP" | jq -r '.[] | "  PR #\(.pullRequest.number)  \(.pullRequest.title)"'
  exit 0
fi

# ── Jump PRs ─────────────────────────────────────────────────────────
# GitHub's enqueuePullRequest(jump: true) errors on PRs already in the
# queue, so we dequeue first, then re-enqueue with jump: true.
#
# Process in reverse order: the last PR in the desired suffix is jumped
# first (to position 1), then the next-to-last (pushing the previous
# one down), etc.  After all jumps the suffix lands in the desired
# order right after the already-correct prefix.

DEQUEUE='
mutation($prId: ID!) {
  dequeuePullRequest(input: { id: $prId }) {
    mergeQueueEntry { id }
  }
}'

ENQUEUE='
mutation($prId: ID!) {
  enqueuePullRequest(input: { pullRequestId: $prId, jump: true }) {
    mergeQueueEntry {
      position
      pullRequest { number title }
    }
  }
}'

REVERSED=$(echo "$TO_JUMP" | jq 'reverse')

for i in $(seq 0 $((JUMP_COUNT - 1))); do
  PR_ID=$(echo "$REVERSED" | jq -r ".[$i].pullRequest.id")
  PR_NUM=$(echo "$REVERSED"  | jq -r ".[$i].pullRequest.number")
  PR_TITLE=$(echo "$REVERSED" | jq -r ".[$i].pullRequest.title")

  echo "  Jumping PR #$PR_NUM: $PR_TITLE"

  # Step 1: dequeue (takes the PR node ID, not the entry ID)
  DEQUEUE_RESULT=$(gh api graphql -f query="$DEQUEUE" -f prId="$PR_ID" 2>&1) || {
    echo "    ERROR (dequeue): $DEQUEUE_RESULT" >&2
    continue
  }

  # Step 2: re-enqueue with jump
  ENQUEUE_RESULT=$(gh api graphql -f query="$ENQUEUE" -f prId="$PR_ID" 2>&1) || {
    echo "    ERROR (enqueue): $ENQUEUE_RESULT" >&2
    continue
  }

  NEW_POS=$(echo "$ENQUEUE_RESULT" | jq -r '.data.enqueuePullRequest.mergeQueueEntry.position')
  echo "    → new position: #$NEW_POS"
done

# ── Show final state ─────────────────────────────────────────────────

echo ""
echo "=== Updated merge queue ==="
RESULT=$(gh api graphql \
  -f query="$QUERY" \
  -f owner="$OWNER" \
  -f repo="$REPO" \
  -f branch="$BRANCH")

echo "$RESULT" | jq -r '
  .data.repository.mergeQueue.entries.nodes[] |
  "  #\(.position)  PR #\(.pullRequest.number)  [\(.state)]  \(.pullRequest.title)  (\([.pullRequest.labels.nodes[].name] | join(", ")))"'
