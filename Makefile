# Chirp -- developer entry points.
.DEFAULT_GOAL := help
SERVICES := auth user post graph timeline search notification messaging media moderation
COMPOSE := docker compose

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## Create .env from the example if it does not exist
	@test -f .env || (cp .env.example .env && \
	  python3 -c "import secrets,pathlib; p=pathlib.Path('.env'); p.write_text(p.read_text().replace('replace-me-with-a-long-random-value-before-running', secrets.token_urlsafe(48)))" && \
	  echo "created .env with a generated JWT_SECRET")

.PHONY: up
up: env ## Build and start the whole stack
	$(COMPOSE) up --build -d
	@echo "gateway      -> http://localhost:8000/docs"
	@echo "auth         -> http://localhost:8001/docs"
	@echo "user         -> http://localhost:8002/docs"
	@echo "post         -> http://localhost:8003/docs"
	@echo "graph        -> http://localhost:8004/docs"
	@echo "timeline     -> http://localhost:8005/docs"
	@echo "search       -> http://localhost:8006/docs"
	@echo "notification -> http://localhost:8007/docs"
	@echo "messaging    -> http://localhost:8008/docs"
	@echo "media        -> http://localhost:8009/docs"
	@echo "moderation   -> http://localhost:8010/docs"
	@echo "grafana      -> http://localhost:3000"
	@echo "prometheus   -> http://localhost:9090"

.PHONY: down
down: ## Stop the stack, keep volumes
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and delete all data
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail logs from every service
	$(COMPOSE) logs -f --tail=100

.PHONY: ps
ps: ## Show container and health status
	$(COMPOSE) ps

.PHONY: install
install: ## Install the shared library and every service in editable mode
	pip install -e libs/chirp-common
	@for s in $(SERVICES); do pip install -e "services/$$s[dev]" --no-deps; done
	pip install pytest pytest-asyncio aiosqlite httpx ruff mypy

.PHONY: test
test: ## Run every service's unit suite (SQLite, no containers needed)
	@set -e; for s in $(SERVICES); do \
	  echo "== $$s"; (cd services/$$s && python -m pytest -q); \
	done

.PHONY: test-integration
test-integration: ## Run the suites against the PostgreSQL in Compose
	@set -e; for s in $(SERVICES); do \
	  echo "== $$s (postgres)"; \
	  (cd services/$$s && TEST_DATABASE_URL="postgresql+asyncpg://chirp:$$(grep '^POSTGRES_PASSWORD=' ../../.env | cut -d= -f2)@localhost:5432/chirp_$$s_test" python -m pytest -q); \
	done

.PHONY: lint
lint: ## Lint and type-check
	ruff check libs services scripts
	ruff format --check libs services scripts
	mypy libs/chirp-common/chirp_common

.PHONY: format
format: ## Auto-format
	ruff format libs services scripts
	ruff check --fix libs services scripts

.PHONY: migrate
migrate: ## Apply migrations for every service
	@for s in $(SERVICES); do $(COMPOSE) run --rm $$s-migrate; done

.PHONY: seed
seed: ## Generate development data (SIZE=small|medium|large)
	python scripts/seed.py --size $(or $(SIZE),small)

.PHONY: health
health: ## Curl every readiness endpoint
	@for p in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010; do echo "-- :$$p"; curl -fsS http://localhost:$$p/health/ready | python3 -m json.tool || true; done

.PHONY: metrics
metrics: ## Show request metrics from every service
	@for p in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010; do echo "-- :$$p"; curl -fsS http://localhost:$$p/metrics | grep -E '^chirp_http_requests_total' | head -3 || true; done
