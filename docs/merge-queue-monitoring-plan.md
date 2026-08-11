# Merge Queue Health Monitoring — Implementation Plan

## Goal

Detect merge queue health problems and notify the team via Slack before people notice. Two complementary detections cover acute failure bursts and slow degradation. Notifications use Block Kit for clean visual design, with aggressive suppression to avoid noise.

## Architecture

Two independent GitHub Actions workflows. No stored state — all decisions derived from GitHub API queries at runtime.

```
merge_group event ──► merge-queue-dequeue-alert.yml ──► Slack (on 3rd dequeue in 30 min)

every 5 min ────────► merge-queue-health-poll.yml ───► Slack (on transition to/from unhealthy)
```

### Secret

Store the Slack webhook URL as a repo-level Actions secret: `SLACK_WEBHOOK_URL`.

---

## Detection 1: Dequeue Burst Alert

**File:** `.github/workflows/merge-queue-dequeue-alert.yml`

**Trigger:** `merge_group` event (fires when a PR is dequeued / checks fail).

**Logic:**

1. Query the GitHub API for recent runs of this same workflow within the last 30 minutes.
2. Count completed runs (excluding the current run).
3. If exactly 2 prior runs exist (meaning the current run is the 3rd dequeue in 30 minutes), send the Slack alert.
4. If the count is not exactly 2, exit silently.

**Suppression:** Alerting on exactly the 3rd dequeue (not 4th, 5th, etc.) naturally self-suppresses. If failures continue past the 30-minute window, a new window starts and the team gets one more alert — which is desirable since it signals "still broken."

**No recovery notification.** This is a point-in-time burst warning. If the burst leads to a sustained problem, Detection 2 catches it and provides recovery lifecycle.

**API queries needed:**

```bash
# List recent runs of this workflow, filtered to last 30 minutes
gh run list \
  --workflow merge-queue-dequeue-alert.yml \
  --json databaseId,createdAt,status \
  --limit 10
```

Filter results to `createdAt >= (now - 30 minutes)` and exclude the current run ID (`${{ github.run_id }}`).

---

## Detection 2: Queue Backup Detection

**File:** `.github/workflows/merge-queue-health-poll.yml`

**Trigger:** `schedule: cron: '*/5 * * * *'`

**Logic:**

1. Query the merge queue via GraphQL for current entries.
2. If the queue is empty, exit early (nothing to worry about).
3. If entries exist, check whether anything has merged to `devel` in the last 60 minutes (query recent commits/pushes on `devel`).
4. If the queue has entries AND nothing has merged in 60 minutes, the queue is **unhealthy**.
5. Check whether the previous run of this workflow also detected an unhealthy state (query the most recent prior run's outputs or conclusion).
6. **Alert on transition to unhealthy** — send Slack alert only if the current state is unhealthy AND the previous run's state was healthy. This fires exactly once when the queue goes unhealthy.
7. **Alert on transition to healthy** — send Slack recovery notification only if the current state is healthy AND the previous run's state was unhealthy.

**Transition detection approach:**

The workflow outputs its health assessment as a job output (e.g., `health=unhealthy` or `health=healthy`). Each run queries the most recent prior completed run of itself via the API and reads its output to determine the previous state. This is fully stateless — the run history *is* the state.

**API queries needed:**

```graphql
# Current merge queue entries
{
  repository(owner: "syntara-orchestration", name: "syntara") {
    mergeQueue(branch: "devel") {
      entries(first: 10) {
        nodes {
          position
          state
          enqueuedAt
          pullRequest { number title }
        }
      }
    }
  }
}
```

```bash
# Recent merges to devel (last 60 minutes)
gh api repos/{owner}/{repo}/commits \
  --jq '.[].commit.committer.date' \
  -f sha=devel \
  -f since="$(date -u -v-60M +%Y-%m-%dT%H:%M:%SZ)"
```

```bash
# Previous run of this workflow (for transition detection)
gh run list \
  --workflow merge-queue-health-poll.yml \
  --status completed \
  --json databaseId,conclusion \
  --limit 1
```

---

## Slack Messages

All messages use Block Kit with a consistent layout: header section, context fields, action button. Color-coded attachment bar distinguishes alert from recovery at a glance.

### Dequeue Burst Alert

- **Color:** Red (`#dc3545`)
- **Header:** `:warning: Merge queue: multiple PRs ejected`
- **Fields:**
  - Dequeue count in the last 30 minutes
  - List of affected PR numbers (linked)
- **Action:** Button linking to the merge queue page

### Queue Backup Alert

- **Color:** Red (`#dc3545`)
- **Header:** `:warning: Merge queue: backed up`
- **Fields:**
  - Current queue depth
  - Time since last successful merge to `devel`
- **Action:** Button linking to the merge queue page

### Queue Backup Recovery

- **Color:** Green (`#28a745`)
- **Header:** `:white_check_mark: Merge queue: recovered`
- **Fields:**
  - Approximate incident duration
- **Action:** Button linking to the merge queue page

---

## Merge Queue Configuration Reference

Current settings on `devel` (for threshold context):

| Setting | Value |
|---|---|
| Strategy | ALLGREEN |
| Max entries building | 3 |
| Max entries to merge | 5 |
| Min entries to merge | 1 |
| Check timeout | 60 minutes |
| Merge method | Squash |

---

## Thresholds Summary

| Detection | Threshold | Rationale |
|---|---|---|
| Dequeue burst | 3 dequeues in 30 min | 30 min ≈ one CI cycle; 3 failures in one cycle is systemic |
| Queue backup | Entries queued + 0 merges in 60 min | 60 min = check timeout; if nothing lands in a full timeout cycle, throughput has collapsed |
| Stall poll frequency | Every 5 minutes | Lightweight job; fast detection with minimal Actions cost |

---

## Implementation Checklist

1. [ ] Add `SLACK_WEBHOOK_URL` repo secret
2. [ ] Create `.github/workflows/merge-queue-dequeue-alert.yml`
3. [ ] Create `.github/workflows/merge-queue-health-poll.yml`
4. [ ] Test dequeue alert by manually triggering a `merge_group` event (or temporarily lowering the threshold to 1)
5. [ ] Test queue backup alert by verifying the GraphQL query returns expected data
6. [ ] Test Slack message formatting by sending to a test channel first
7. [ ] Monitor for false positives / missed alerts over 1-2 weeks and tune thresholds
