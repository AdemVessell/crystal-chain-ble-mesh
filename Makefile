SHELL := /bin/sh
PY ?= python3

.PHONY: install test lint sim gradient clean

install:
	"$(PY)" -m pip install -r requirements.txt

test:
	"$(PY)" -m pytest -q

lint:
	"$(PY)" -m ruff check .

sim:
	"$(PY)" scripts/run_crystal_mesh_ledger_sim.py --write-report

gradient:
	"$(PY)" scripts/run_crystal_localization_gradient.py --write-report

clean:
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
