.PHONY: help setup install test lint format clean demo doctor

help:
	@echo "SAAT Development Commands"
	@echo "========================"
	@echo ""
	@echo "setup           Install development dependencies"
	@echo "install         Install package in editable mode"
	@echo "test            Run test suite"
	@echo "test-cov        Run tests with coverage report"
	@echo "lint            Run linters (ruff, black, mypy)"
	@echo "format          Format code with black"
	@echo "clean           Remove build artifacts and caches"
	@echo "demo            Run offline self-tests"
	@echo "doctor          Check system configuration"
	@echo ""

setup:
	python -m venv venv
	. venv/bin/activate && pip install --upgrade pip setuptools wheel
	. venv/bin/activate && pip install -e ".[dev]"

install:
	pip install -e ".[full]"

test:
	pytest tests/

test-cov:
	pytest tests/ --cov=src/saat --cov-report=html --cov-report=term-missing

lint:
	ruff check src/ tests/
	black --check src/ tests/
	mypy src/saat/

format:
	black src/ tests/
	ruff check --fix src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache htmlcov .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

demo:
	saat demo

doctor:
	saat doctor

.venv:
	python -m venv venv
