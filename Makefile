.PHONY: install web test lint serve dev plan backtest benchmark docker

install:            ## Python package with dev tools
	pip install -e ".[dev]"

web:                ## build the buying desk into web/dist
	cd web && npm ci && npm run build

test:
	pytest

lint:
	ruff check inventiq tests scripts && ruff format --check inventiq tests scripts

serve:              ## API and desk on http://127.0.0.1:8000
	python -m inventiq serve

dev:                ## API on :8000 and the desk with hot reload on :5173
	python -m inventiq serve & cd web && npm run dev

plan:
	python -m inventiq plan --budget 20000000 --risk balanced

backtest:
	python -m inventiq backtest

benchmark:
	python scripts/benchmark.py

docker:
	docker compose up --build
