.DEFAULT_GOAL := help
.PHONY: help install run test lint format typecheck check build docker-build clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create the virtualenv and install all dependencies
	uv sync --all-groups

run: ## Run the API locally with auto-reload
	uv run pulsewatch --reload

test: ## Run the test suite
	uv run pytest

lint: ## Check style and common defects
	uv run ruff check .

format: ## Auto-format the source tree
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run static type checking
	uv run mypy src tests

check: lint typecheck test ## Run every quality gate

build: ## Build wheel and source distribution
	uv build

docker-build: ## Build the production container image
	docker build -f docker/Dockerfile -t pulsewatch:dev .

clean: ## Remove local caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
