.DEFAULT_GOAL := help
PY      := .venv/bin/python
PIP     := .venv/bin/pip
MANAGE  := $(PY) manage.py

# Django 5.2 needs Python 3.12+. Override if your interpreter lives elsewhere:
#   make setup PYTHON=/usr/local/bin/python3.12
PYTHON ?= python3.12

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ───────────────────────────── setup ─────────────────────────────

.PHONY: setup
setup: venv install env  ## One-shot first-time setup (venv + deps + .env)
	@echo ""
	@echo "Next:  make infra   →  make migrate   →  make seed   →  make run"

.PHONY: venv
venv:  ## Create the virtualenv
	$(PYTHON) -m venv .venv
	$(PIP) install -U pip wheel

.PHONY: install
install:  ## Install dev dependencies
	$(PIP) install -r requirements-dev.txt

.PHONY: env
env:  ## Create .env from the template if missing
	@test -f .env || (cp .env.example .env && chmod 600 .env && echo "created .env")

# ───────────────────────── infrastructure ────────────────────────

.PHONY: infra
infra:  ## Start Postgres + Redis via docker compose
	docker compose up -d
	@echo "waiting for postgres..."
	@until docker compose exec -T postgres pg_isready -U opstracking >/dev/null 2>&1; do sleep 1; done
	@echo "infra ready"

.PHONY: infra-down
infra-down:  ## Stop infrastructure (keeps data)
	docker compose down

.PHONY: infra-reset
infra-reset:  ## Stop infrastructure AND destroy all data
	docker compose down -v

# ───────────────────────────── django ────────────────────────────

.PHONY: migrate
migrate:  ## Apply database migrations
	$(MANAGE) migrate

.PHONY: migrations
migrations:  ## Generate new migrations
	$(MANAGE) makemigrations

.PHONY: seed
seed:  ## Load demo master data + an admin and an employee account
	$(MANAGE) seed_dev

.PHONY: run
run:  ## Run the HTTP dev server (DRF + pages) on :8000
	$(MANAGE) runserver 0.0.0.0:8000

.PHONY: run-ws
run-ws:  ## Run Daphne (ASGI / websockets) on :8002
	.venv/bin/daphne -b 127.0.0.1 -p 8002 opstracking.asgi:application

.PHONY: worker
worker:  ## Run the Celery default worker
	.venv/bin/celery -A opstracking worker -Q default -l INFO

.PHONY: worker-reports
worker-reports:  ## Run the Celery reports worker
	.venv/bin/celery -A opstracking worker -Q reports -l INFO

.PHONY: beat
beat:  ## Run the Celery beat scheduler
	.venv/bin/celery -A opstracking beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

.PHONY: shell
shell:  ## Django shell (shell_plus if django-extensions is installed)
	$(MANAGE) shell_plus || $(MANAGE) shell

.PHONY: superuser
superuser:  ## Create a Django admin user
	$(MANAGE) createsuperuser

.PHONY: static
static:  ## Collect static files
	$(MANAGE) collectstatic --noinput

# ─────────────────────────── quality ─────────────────────────────

.PHONY: test
test:  ## Run the test suite
	.venv/bin/pytest

.PHONY: cov
cov:  ## Run tests with a coverage report
	.venv/bin/pytest --cov=core --cov=apps --cov=pages --cov-report=term-missing

.PHONY: lint
lint:  ## Lint with ruff
	.venv/bin/ruff check .

.PHONY: fmt
fmt:  ## Auto-format and auto-fix with ruff
	.venv/bin/ruff format .
	.venv/bin/ruff check . --fix

.PHONY: check
check:  ## Django system checks, deploy-strict
	$(MANAGE) check --deploy

.PHONY: clean
clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
