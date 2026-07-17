.PHONY: up down migrate test lint admin demo

up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose run --rm api alembic upgrade head

admin:
	docker compose run --rm api python -m app.cli create-admin

demo:
	docker compose run --rm api python -m app.cli seed-demo

test:
	docker compose run --rm api pytest
	docker compose run --rm web pnpm test

lint:
	docker compose run --rm api ruff check app tests
	docker compose run --rm api mypy app
	docker compose run --rm web pnpm lint
	docker compose run --rm web pnpm typecheck

