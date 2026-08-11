# Development with Git Worktrees

This guide explains how to use Git worktrees for parallel development in the Nexus project.

## Prerequisites

- **Git 2.5+** - Git worktrees were introduced in Git 2.5.0 (July 2015)
  - Check your version: `git --version`
  - Most modern systems have this version or newer


## What are Git Worktrees?

Git worktrees allow you to have multiple working directories attached to the same repository. Each worktree can have a different branch checked out, enabling you to work on multiple branches simultaneously without switching contexts or stashing changes.

## Why Use Worktrees?

- **Parallel Development**: Work on multiple features/branches simultaneously
- **PR Reviews**: Review pull requests without leaving your current work
- **Bug Fixes**: Quickly switch to fix urgent bugs while keeping feature work intact
- **Testing**: Test different branches side-by-side
- **Isolated Environments**: Each worktree can have its own services running with different ports and configurations

## Quick Start

Initialize a new worktree:

```bash
# Basic usage (creates branch from main)
make init-worktree feature-auth

# From a different base branch
make init-worktree bugfix-api develop

# With a specific Python version
make init-worktree feature-payments main python3.12
```

After initialization:

```bash
# Navigate to the new worktree
cd worktrees/feature-auth

# Activate the virtual environment
source .venv/bin/activate

# Update environment variables (if needed)
# You probably want to change PODMAN_PROJECT
nano .env

# Start working!
make run-services
make dev
```

## Initialization Workflow

The `make init-worktree` command performs the following steps automatically:

1. **Creates a git worktree** in `worktrees/<branch-name>/`
2. **Copies optional and relevant non versioned files.** Look at `tools/init-git-worktree.sh` for further details.
3. **Sets up Python environment**:
   - Creates a Python virtual environment (`.venv`)
   - Installs `uv` package manager
   - Runs `make install` to install all project dependencies


## Common Use Cases

Worktrees are useful for both parallel feature development and PR reviews without disrupting your current work.

### Parallel Development and PR Reviews

You're working on a feature but need to work on another feature or review a PR:

```bash
# You're currently in main worktree working on feature-auth
cd ~/repos/nexus

# Create a new worktree (for another feature or PR review)
make init-worktree feature-payments
# or
make init-worktree pr-review-api-refactor

# Navigate to the new worktree
cd worktrees/feature-payments

# Activate environment
source .venv/bin/activate

# Update .env to use different ports and project name
nano .env  # Change PODMAN_PROJECT and ports

# Start services and work
make services-run
make dev

# When done, go back to your original work
cd ~/repos/nexus
source .venv/bin/activate
```

Your original `feature-auth` work remains untouched, and you can switch back anytime!

**Important**: Update environment variables in each worktree to avoid conflicts.

#### Example Configuration for Multiple Worktrees

**Main Repository** (`~/repos/nexus/.env`):
```bash
PODMAN_PROJECT=syntara
APP_API_PORT=8000
APP_DB_PORT=5432
APP_TEMPORAL_UI_PORT=8081
APP_CACHE_PORT=6379
```

**Feature Worktree** (`~/repos/nexus/worktrees/feature-auth/.env`):
```bash
PODMAN_PROJECT=syntara-feature-auth
APP_API_PORT=8001
APP_DB_PORT=5433
APP_TEMPORAL_UI_PORT=8082
APP_CACHE_PORT=6380
```

## Managing Worktrees

### List All Worktrees

```bash
git worktree list
```

Output example:
```
/home/user/repos/nexus              abc1234 [main]
/home/user/repos/nexus/worktrees/feature-auth   def5678 [feature-auth]
/home/user/repos/nexus/worktrees/bugfix-api     ghi9012 [bugfix-api]
```

### Switch Between Worktrees

Simply navigate to the directory:

```bash
# Switch to feature-auth worktree
cd ~/repos/nexus/worktrees/feature-auth
source .venv/bin/activate

# Switch back to main worktree
cd ~/repos/nexus
source .venv/bin/activate
```

### Remove a Worktree

When you're done with a worktree:

```bash
# Remove the worktree
git worktree remove worktrees/feature-auth

# Alternative: If the worktree has uncommitted changes
git worktree remove worktrees/feature-auth --force
```

**Important**: Removing a worktree does **not** delete the branch. The branch still exists in your repository.

If you also want to delete the branch:

```bash
# Delete the branch (only if it's fully merged)
git branch -d feature-auth

# Force delete the branch (even if not merged)
git branch -D feature-auth
```

### Prune Deleted Worktrees

If you manually deleted a worktree directory, clean up git's records:

```bash
git worktree prune
```

## Environment Variables Configuration

After initializing a worktree, you should review and update the `.env` file to avoid conflicts with other running instances.


### Why Change PODMAN_PROJECT?

The `PODMAN_PROJECT` variable determines the project name for `podman-compose`, which affects:

- Container names: `${PODMAN_PROJECT}_database_1`, `${PODMAN_PROJECT}_redis_1`, etc.
- Network names: `${PODMAN_PROJECT}_default`
- Volume names: `${PODMAN_PROJECT}_syntara_postgres_data`

Setting different `PODMAN_PROJECT` values ensures complete isolation between worktrees.


## Troubleshooting

### Error: "fatal: 'worktrees/feature-name' already exists"

The worktree directory already exists. Either:

```bash
# Remove the existing worktree
git worktree remove worktrees/feature-name

# Or use a different name
make init-worktree BRANCH=feature-name-v2
```

### Error: "fatal: invalid reference: feature-name"

The branch doesn't exist remotely. The script will try to create it from the base branch, but if that fails:

```bash
# Create the branch manually first
git checkout -b feature-name main
git checkout main

# Then create the worktree
make init-worktree BRANCH=feature-name
```

### Port Already in Use

If services fail to start due to port conflicts:

1. Check which ports are in use: `podman ps`
2. Update `.env` in your worktree with different ports
3. Restart services: `make services-run`

### Python Version Not Found

If the specified Python version isn't available:

```bash
# Check available Python versions
ls /usr/bin/python*

# Use an available version
make init-worktree BRANCH=feature-name PYTHON=python3.12
```

### Shared Database Concerns

Each worktree can have its own isolated database when using different `PODMAN_PROJECT` values. However, if you want to share data:

1. Use the same `PODMAN_PROJECT` in both `.env` files
2. Be aware that database migrations and data will be shared
3. Consider potential conflicts carefully

### Removing a Worktree with Uncommitted Changes

```bash
# Git will prevent removal by default
git worktree remove worktrees/feature-name
# error: contains modified or untracked files

# Force removal (be careful!)
git worktree remove worktrees/feature-name --force
```

### Claude Code Warning: "imports files outside the current working directory"

When using Claude Code inside a worktree, you may see this warning:

```
⚠️  This project's CLAUDE.md imports files outside the current working directory.
    Never allow this for third-party repositories.
```

**This warning is expected and safe to ignore** for the following reasons:

1. **It's your own project**: The warning is a security measure for third-party repositories
2. **Git worktrees work this way**: In a worktree, the `.git` directory is actually a file pointing to the main repository's `.git/worktrees/` structure
3. **Files are present locally**: All referenced files (`CLAUDE.md`, `AGENTS.md`, etc.) are actually present in your worktree

**Why it happens**: Git worktrees share the same git object database with the main repository. Claude Code detects this internal structure and warns you as a precaution against malicious third-party repos.

**Action**: You can safely dismiss this warning when working in your own worktrees.

## Additional Resources

- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- [Nexus Development Guide](../README.md)
- [Podman Compose Documentation](https://github.com/containers/podman-compose)
