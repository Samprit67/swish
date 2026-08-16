.PHONY: help install dev check lint format type test cov serve docker clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## install the package
	pip install -e .

dev:  ## install with dev dependencies
	pip install -e ".[dev]"

check: lint type test  ## run everything CI runs

lint:  ## ruff check + format check
	ruff check swish tests
	ruff format --check swish tests

format:  ## apply ruff formatting
	ruff check --fix swish tests
	ruff format swish tests

type:  ## mypy
	mypy swish

test:  ## pytest
	pytest

cov:  ## pytest with coverage
	pytest --cov=swish --cov-report=term-missing

serve:  ## run the dashboard
	python -m swish serve

docker:  ## build the image
	docker build -t swish:latest .

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis .coverage coverage.xml htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +
