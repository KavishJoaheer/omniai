PYTHON ?= python
NPM ?= npm

.PHONY: backend-install frontend-install install backend-dev frontend-dev dev

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

