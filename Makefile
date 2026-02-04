.PHONY: dev test lint format

dev:
	python -m uvicorn segfault.api.app:app --reload

test:
	python -m pytest -q

lint:
	python -m ruff check segfault

format:
	python -m black segfault
