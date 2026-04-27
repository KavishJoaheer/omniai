PYTHON ?= python
NPM ?= npm
COMPOSE ?= docker compose -f deploy/compose/docker-compose.yml

.PHONY: backend-install frontend-install install backend-dev frontend-dev dev \
        compose-up compose-down compose-logs migrate revision

backend-install:
	$(PYTHON) -m pip install -e ./backend

frontend-install:
	cd frontend && $(NPM) install

install: backend-install frontend-install

backend-dev:
	uvicorn omniai.interfaces.http.app:create_app --factory --reload --app-dir backend

frontend-dev:
	cd frontend && $(NPM) run dev

dev:
	@echo "Run 'make backend-dev' and 'make frontend-dev' in separate terminals."

compose-up:
	$(COMPOSE) up -d

compose-down:
	$(COMPOSE) down

compose-logs:
	$(COMPOSE) logs -f api

migrate:
	cd backend && alembic upgrade head

revision:
	cd backend && alembic revision --autogenerate -m "$(m)"

