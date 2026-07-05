.PHONY: help up down build logs test migrate shell

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start all services
	docker compose up -d

up-build: ## Rebuild and start all services
	docker compose up -d --build

down: ## Stop all services
	docker compose down

logs: ## Tail logs for all services
	docker compose logs -f

logs-api: ## Tail API logs
	docker compose logs -f api

logs-worker: ## Tail worker logs
	docker compose logs -f worker

build: ## Build all images
	docker compose build

test: ## Run backend tests
	cd backend && python -m pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage
	cd backend && python -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

migrate: ## Run database migrations
	cd backend && alembic upgrade head

migrate-create: ## Create a new migration (usage: make migrate-create msg="description")
	cd backend && alembic revision --autogenerate -m "$(msg)"

shell: ## Open a shell in the API container
	docker compose exec api bash

db-shell: ## Open a psql shell
	docker compose exec postgres psql -U djs_user -d distributed_job_scheduler

redis-cli: ## Open Redis CLI
	docker compose exec redis redis-cli

format: ## Format backend code
	cd backend && python -m black src/ tests/ && python -m isort src/ tests/

lint: ## Lint backend code
	cd backend && python -m ruff check src/ tests/

seed: ## Seed database with sample data
	cd backend && python -m src.seed
