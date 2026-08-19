DC ?= docker compose
BACKEND := $(DC) exec -T backend
MANAGE := $(BACKEND) python manage.py

.DEFAULT_GOAL := help
.PHONY: help up down restart build logs ps migrate migrations migrations-check \
        seed seed-roles seed-demo test test-unit lint fmt shell psql superuser \
        verify-audit permissions-matrix clean backup restore

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ lifecycle

up: ## Start the stack (db, redis, backend, worker, beat, frontend)
	$(DC) up -d --build
	@echo "API      http://localhost:8000/api/v1/"
	@echo "Swagger  http://localhost:8000/api/v1/schema/swagger-ui/"
	@echo "Admin    http://localhost:8000/admin/"
	@echo "PWA      http://localhost:3000"

down: ## Stop the stack (keeps the database volume)
	$(DC) down

restart: ## Restart application services
	$(DC) restart backend worker beat

build: ## Rebuild images
	$(DC) build

logs: ## Tail logs from all services
	$(DC) logs -f

ps: ## Show service status
	$(DC) ps

# ------------------------------------------------------------------ database

migrate: ## Apply migrations
	$(MANAGE) migrate

migrations: ## Generate migrations after model changes
	$(MANAGE) makemigrations

migrations-check: ## Fail if models drift from migrations (used by CI)
	$(MANAGE) makemigrations --check --dry-run

psql: ## Open a psql session against the dev database
	$(DC) exec db psql -U $${POSTGRES_USER:-uniacmis} -d $${POSTGRES_DB:-uniacmis}

backup: ## Run a database backup now (NFR-DATA-01) — see scripts/backup_database.sh
	./scripts/backup_database.sh

restore: ## Restore a backup: make restore FILE=backups/uniacmis-....sql.gz
	./scripts/restore_database.sh "$(FILE)" --yes

# --------------------------------------------------------------------- seeding

seed: seed-roles seed-demo ## Seed roles and demo data

seed-roles: ## Apply the RBAC policy (idempotent, production-safe)
	$(MANAGE) seed_roles

seed-demo: ## Seed demo institution, curriculum and students (development only)
	$(MANAGE) seed_demo

superuser: ## Create a superuser interactively
	$(DC) exec backend python manage.py createsuperuser

# ----------------------------------------------------------------------- tests

test: ## Run the full test suite with coverage
	$(BACKEND) pytest --cov --cov-report=term-missing

test-unit: ## Run unit tests only (fast loop)
	$(BACKEND) pytest -m "not integration" -q

permissions-matrix: ## Print the role x endpoint permission matrix
	$(MANAGE) permission_matrix

verify-audit: ## Re-walk and verify the audit log hash chain
	$(MANAGE) verify_audit_chain

# --------------------------------------------------------------------- quality

lint: ## Run ruff, black --check and the import-linter contracts
	$(BACKEND) ruff check .
	$(BACKEND) black --check .
	$(BACKEND) lint-imports

fmt: ## Auto-format with black and ruff --fix
	$(BACKEND) ruff check --fix .
	$(BACKEND) black .

shell: ## Django shell
	$(DC) exec backend python manage.py shell

clean: ## Remove containers AND volumes (destroys local data)
	$(DC) down -v
