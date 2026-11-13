.DEFAULT_GOAL := help
.PHONY: help install run migrate test test-integration lint format format-check typecheck verify-unit check build docker-build clean

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Create the virtualenv and install all dependencies
	uv sync --all-groups

run: migrate ## Apply migrations, then run the API locally with auto-reload
	uv run pulsewatch --reload

migrate: ## Apply PostgreSQL migrations
	uv run pulsewatch-migrate

test: ## Run the test suite
	uv run pytest

test-integration: ## Run tests that require PostgreSQL
	@test -n "$$PULSEWATCH_TEST_DATABASE_URL" || { \
		echo "PULSEWATCH_TEST_DATABASE_URL is required for integration tests" >&2; \
		exit 1; \
	}
	uv run pytest --no-cov -m integration

lint: ## Check style and common defects
	uv run ruff check .

format: ## Auto-format the source tree
	uv run ruff format .
	uv run ruff check --fix .

format-check: ## Verify formatting without changing files
	uv run ruff format --check .

typecheck: ## Run static type checking
	uv run mypy src tests

verify-unit: ## Verify the systemd unit without installing it
	./scripts/verify-systemd-unit.sh

check: format-check lint typecheck test verify-unit ## Run every quality gate

build: ## Build wheel and source distribution
	uv build

docker-build: ## Build the production container image
	docker build -f docker/Dockerfile -t pulsewatch:dev .

clean: ## Remove local caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
