PY ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: install test lint format demo mock spec serve-mock clean

install:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e ".[dev]"

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check src tests scripts
	$(BIN)/ruff format --check src tests scripts

format:
	$(BIN)/ruff format src tests scripts
	$(BIN)/ruff check --fix src tests scripts

demo:
	$(BIN)/python scripts/demo.py

mock:
	$(BIN)/zoho-mock-server --port 8800

spec:
	$(BIN)/zoho-inventory-mcp export-spec --out docs/tool-spec.json

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache build dist *.egg-info
