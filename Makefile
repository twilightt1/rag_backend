.PHONY: dev build up down migrate seed test lint

dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

migrate:
	alembic upgrade head

makemigration:
	alembic revision --autogenerate -m "$(name)"

worker:
	celery -A app.tasks.celery_app worker -Q default,ingestion,email -c 4 -l INFO

beat:
	celery -A app.tasks.celery_app beat -l INFO

test:
	pytest tests/ -v --asyncio-mode=auto

lint:
	ruff check app/ && mypy app/ --ignore-missing-imports

format:
	ruff format app/
