# Lore: common commands. Run `make help` to list them.
# Backend commands run inside backend/ and load the root .env first (if it exists).

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Shell snippet: export every variable from ../.env (we are inside backend/ when it runs).
LOAD_ENV = set -a; [ -f ../.env ] && . ../.env; set +a;
BACKEND  = cd backend && $(LOAD_ENV)

# Which container `make aws-logs` follows: api or falkordb.   Example: make aws-logs CONTAINER=falkordb
CONTAINER ?= api

.PHONY: help setup db db-lite down gen text load load-fake api web mock test test-all lint eval mcp reset \
        aws-deploy aws-secrets aws-secrets-from-env aws-frontend aws-backend aws-status aws-logs aws-destroy

help: ## Show this list of commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-20s %s\n", $$1, $$2}'

setup: ## Install backend (uv sync) and frontend (npm install) dependencies
	cd backend && uv sync
	cd frontend && npm install

db: ## Start FalkorDB in Docker (port 6379; the server image has no Browser UI)
	docker compose up -d falkordb

db-lite: ## No Docker? Run a real FalkorDB via FalkorDBLite on port 6390 (set LORE_FALKORDB_PORT=6390)
	uv run --no-project --python 3.12 --with falkordblite python scripts/falkordb_lite.py 6390

down: ## Stop all containers (keeps the graph data)
	docker compose down

gen: ## Generate the structured fake-company data into backend/data/*.json
	$(BACKEND) uv run python -m lore.data_gen.generate

text: ## Generate Slack/ticket/ADR text with Gemini Flash (needs a key; run once, commit the result)
	$(BACKEND) uv run python -m lore.data_gen.text_gen

load: ## Wipe and reload the graph from backend/data (real embeddings, needs a Gemini key)
	$(BACKEND) uv run python -m lore.loader.load --reset

load-fake: ## Same as load, but with fake embeddings (no Gemini key needed)
	$(BACKEND) uv run python -m lore.loader.load --reset --fake-embeddings

api: ## Run the API with auto-reload on http://localhost:8000
	$(BACKEND) uv run uvicorn lore.api.main:app --reload --port 8000

web: ## Run the web page on http://localhost:5173 (talks to the API)
	cd frontend && npm run dev

mock: ## Run the web page on fake data only (no backend needed)
	cd frontend && VITE_MOCK=1 npm run dev

test: ## Run fast tests (no FalkorDB, no Gemini needed)
	$(BACKEND) uv run pytest -m "not integration and not live_llm"

test-all: ## Run every test (needs FalkorDB loaded and a Gemini key)
	$(BACKEND) uv run pytest

lint: ## Check code style: ruff for Python, npm run lint for the frontend
	cd backend && uv run ruff check .
	cd frontend && npm run lint

eval: ## Run the golden questions, Graph ON and OFF, and write backend/eval/report.md
	$(BACKEND) uv run python -m eval.run --mode both

mcp: ## Run the MCP server (same tools as the agents, for Gemini CLI etc.)
	$(BACKEND) uv run python -m lore.mcp_server

# ---- AWS (see infra/README.md). All of these call infra/deploy.sh; the region is ap-south-1.
aws-deploy: ## AWS: create/update everything (network, registry, image build, app, website)
	infra/deploy.sh deploy

aws-secrets: ## AWS: fill the secret lore/app (asks for the keys with hidden input)
	infra/deploy.sh secrets

aws-secrets-from-env: ## AWS: same, but read Gemini/Slack/GitHub from the root .env
	infra/deploy.sh secrets --from-env

aws-frontend: ## AWS: rebuild the React app and publish it (S3 + CloudFront)
	infra/deploy.sh frontend-only

aws-backend: ## AWS: rebuild the API image in CodeBuild and redeploy the app
	infra/deploy.sh backend-only

aws-status: ## AWS: stacks, running task, load balancer health, public URL
	infra/deploy.sh status

aws-logs: ## AWS: follow container logs (CONTAINER=api or falkordb)
	infra/deploy.sh logs $(CONTAINER)

aws-destroy: ## AWS: delete everything (asks you to type "lore")
	infra/deploy.sh destroy

reset: ## Delete the FalkorDB data volume and restart an empty database (then run make load)
	docker compose down -v
	docker compose up -d falkordb
