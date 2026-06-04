.PHONY: install api worker web test fmt seed up down docs docs-serve docs-build

install:
	python -m venv .venv && . .venv/bin/activate && pip install -e ".[server,dev,llm]"
	cd frontend && npm install

api:
	uvicorn backend.app.main:app --reload --port 8000

worker:
	celery -A workers.celery:celery worker --loglevel=info

web:
	cd frontend && npm run dev

test:
	pytest -q

fmt:
	ruff check --fix shared backend workers

seed:
	python3 scripts/seed_demo.py

up:
	docker compose up --build

down:
	docker compose down

docs: docs-serve         # alias

docs-serve:              # live-reload docs at http://localhost:8001
	mkdocs serve -a localhost:8001

docs-build:              # strict build into ./site (fails on broken links/nav)
	mkdocs build --strict
