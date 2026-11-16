.PHONY: help setup-env up down logs test lint format api-shell
help:
	@echo "Targets: setup-env up down logs test lint format"
setup-env:
	@test -f .env || cp .env.example .env
up: setup-env
	docker compose up --build

down:
	docker compose down
logs:
	docker compose logs -f --tail=200

test:
	cd backend && python -m pytest
lint:
	cd backend && ruff check . && mypy app
format:
	cd backend && ruff format .
api-shell:
	docker compose exec api sh
