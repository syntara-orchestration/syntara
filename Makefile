.PHONY: help install format lint test test-all typecheck dev gen-contracts \
       services-up services-down services-logs secrets db-migrate db-seed admin-password setup sync \
       pre-commit-install

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Development workflow ---

install: ## Install backend and frontend dependencies
	$(MAKE) -C backend install
	cd frontend && npm ci
	$(MAKE) pre-commit-install

pre-commit-install: ## Install pre-commit hooks
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg

dev: ## Start backend API, Temporal workers, and frontend dev servers
	$(MAKE) -C backend dev &
	$(MAKE) -C backend worker-run &
	$(MAKE) -C backend background-worker-run &
	cd frontend && VITE_API_URL=https://localhost:8000 npm run start

setup: _ensure-env install secrets certs build-images services-up db-migrate db-seed admin-password ## One-shot bootstrap: install, secrets, certs, services, migrations, seed
	@echo ""
	@echo "Setup complete. Run 'make dev' to start the development servers."

_ensure-env:
	@if [ ! -f backend/.env ]; then \
		cp backend/.env.example backend/.env; \
		echo "Created backend/.env from .env.example"; \
	fi

# --- Code quality ---

format: ## Format both codebases
	$(MAKE) -C backend format
	cd frontend && npm run format

lint: ## Lint both codebases
	$(MAKE) -C backend lint
	cd frontend && npm run lint

test: ## Run backend and frontend tests
	$(MAKE) -C backend test
	cd frontend && npm test

test-all: ## Run all tests including integration
	$(MAKE) -C backend test-all
	cd frontend && npm test

typecheck: ## Type-check both codebases
	$(MAKE) -C backend typecheck
	cd frontend && npx tsc --noEmit

# --- Infrastructure services (delegated to backend which has the correct venv context) ---

services-up: ## Start all infrastructure services in background
	$(MAKE) -C backend services-run

services-down: ## Stop all services
	$(MAKE) -C backend services-stop

services-logs: ## Tail logs from all services
	$(MAKE) -C backend services-logs

# --- Database & secrets ---

secrets: ## Generate JWT keys, admin password, encryption key
	$(MAKE) -C backend secrets-generate

certs: ## Generate self-signed TLS certificates for local development
	$(MAKE) -C backend certs-generate

build-images: ## Build container images
	$(MAKE) -C backend build-images

db-migrate: ## Run database migrations
	cd backend && APP_ADMIN_PASSWORD_PATH=.secrets/admin-password uv run alembic upgrade head

db-seed: ## Seed the database with required data
	$(MAKE) -C backend db-seed

admin-password: ## Sync bootstrap admin password from .secrets/admin-password into the database
	$(MAKE) -C backend admin-password

# --- Contract generation ---

gen-contracts: ## Regenerate TypeScript types from backend OpenAPI specs
	cd frontend/packages/syntara-contracts && npm run gen:local

# --- Standards checks (removed from pre-commit, run in CI) ---

run-standards-checks-frontend: ## Run frontend standards checks (contract generation)
	cd frontend/packages/syntara-contracts && npm run gen:ts
	@git diff --exit-code frontend/packages/syntara-contracts/src/ || { \
		echo "Generated contracts have uncommitted changes. Commit them."; \
		exit 1; \
	}

run-standards-checks-backend: ## Run backend standards checks (API specs, code quality)
	$(MAKE) -C backend api-spec-validation
	$(MAKE) -C backend api-spec-bundle
	@git diff --exit-code backend/src/syntara/schemas/openapi.yaml || { \
		echo "Bundled OpenAPI spec has uncommitted changes. Commit them."; \
		exit 1; \
	}
	$(MAKE) -C backend api-spec-drift
	$(MAKE) -C backend generate-api-client
	@git diff --exit-code backend/src/api_client/ || { \
		echo "Generated API client has uncommitted changes. Commit them."; \
		exit 1; \
	}
	$(MAKE) -C backend check-api-paths
	$(MAKE) -C backend check-dead-code
	$(MAKE) -C backend check-cycles
	$(MAKE) -C backend check-orphans
	$(MAKE) -C backend check-openapi-breaking-pre-commit
	$(MAKE) -C backend verify-test-structure

run-standards-checks-all: run-standards-checks-frontend run-standards-checks-backend ## Run all standards checks (frontend + backend)

# --- Upstream sync (transition period) ---

sync: ## Pull latest changes from upstream syntara repos
	bash scripts/sync-from-upstream.sh
