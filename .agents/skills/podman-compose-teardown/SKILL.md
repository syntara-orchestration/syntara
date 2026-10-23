---
name: podman-compose-teardown
description: "Tear down any running podman-compose environment and clean up containers. Pass --purge to also delete volumes."
user-invocable: true
---

Tear down any running Syntara podman-compose environment on the local machine. Stops all containers, removes them, and cleans up the network.

**Usage:**
- `/podman-compose-teardown` — stop and remove all containers, keep data volumes
- `/podman-compose-teardown --purge` — stop, remove, **and delete all volumes** (database, audit exports)

**Parse the argument:** check if the user passed `--purge`. If the argument string contains `--purge`, set purge mode to true.

## Phase 1: Detect existing environments

1. **List all syntara containers** (including stopped) and volumes to show the user what will be cleaned up:

   ```bash
   podman ps -a --format '{{.Names}}' | grep -E '^syntara_' || echo "No syntara containers found"
   podman volume ls --format '{{.Name}}' | grep -E '^syntara_' || echo "No syntara volumes found"
   ```

2. **Show compose service status** if any syntara containers exist:

   ```bash
   cd backend && uv run podman-compose -p syntara -f ../podman-compose.yml ps 2>/dev/null || true
   ```

3. If no syntara containers exist **and** either `--purge` was not passed or no syntara volumes exist, tell the user there is nothing to tear down and stop.

## Phase 2: Stop and remove

1. **Stop all services** including optional profiles:

   ```bash
   cd backend && uv run podman-compose -p syntara -f ../podman-compose.yml --profile mcp-scenarios --profile telemetry-e2e down 2>/dev/null || true
   ```

2. **Check for orphaned containers** that were not removed by compose:

   ```bash
   podman ps -a --format '{{.Names}}' | grep -E '^syntara_'
   ```

   If any remain, force-remove them:

   ```bash
   podman ps -a --format '{{.Names}}' | grep -E '^syntara_' | xargs -r podman rm -f
   ```

## Phase 3: Purge volumes (only if `--purge` was passed)

Skip this phase entirely if `--purge` was not passed.

1. **List syntara volumes:**

   ```bash
   podman volume ls --format '{{.Name}}' | grep -E '^syntara_'
   ```

2. **Warn the user before deleting:**

   > This will delete all persistent data including the PostgreSQL database and audit exports. You will need to re-run `make db-migrate`, `make db-seed`, and `make admin-password` next time you spin up the environment.

3. **Remove the volumes:**

   ```bash
   podman volume ls --format '{{.Name}}' | grep -E '^syntara_' | xargs -r podman volume rm
   ```

4. **Confirm volumes are gone:**

   ```bash
   podman volume ls --format '{{.Name}}' | grep -E '^syntara_' || echo "All syntara volumes removed"
   ```

## Phase 4: Verify and report

1. **Confirm no syntara containers remain:**

   ```bash
   podman ps -a --format '{{.Names}}' | grep -E '^syntara_' || echo "All syntara containers removed"
   ```

2. **Report to the user** with a summary:
   - How many containers were stopped and removed
   - Whether volumes were purged (if `--purge` was used) and how many were removed
   - If volumes were preserved, note that database data is intact for next startup
   - How to bring the environment back up: `/podman-compose-spinup-pr <PR>` or `make services-up`
