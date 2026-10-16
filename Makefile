# Lore: common commands. Run `make help` to list them.
# Backend commands run inside backend/ and load the root .env first (if it exists).

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Shell snippet: export every variable from ../.env (we are inside backend/ when it runs).
LOAD_ENV = set -a; [ -f ../.env ] && . ../.env; set +a;
BACKEND  = cd backend && $(LOAD_ENV)

# TODO(Ayan): fill in once you have a VM. Example: VM_HOST=ubuntu@203.0.113.10 make deploy
VM_HOST ?=
VM_DIR  ?= ~/lore

.PHONY: help setup db db-lite down gen text load load-fake api web mock test test-all lint eval mcp deploy reset

help: ## Show this list of commands
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

setup: ## Install backend (uv sync) and frontend (npm install) dependencies
	cd backend && uv sync
	cd frontend && npm install

db: ## Start FalkorDB in Docker (port 6379, Browser on http://localhost:3000)
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

deploy: ## Copy the repo to the VM and start the prod stack (set VM_HOST first)
	@if [ -z "$(VM_HOST)" ]; then \
	  echo "TODO: set VM_HOST, e.g.  VM_HOST=ubuntu@203.0.113.10 make deploy"; \
	  echo "      The VM needs Docker + the compose plugin, and a copy of .env (see docs/RUNBOOK.md)."; \
	  exit 1; \
	fi
	rsync -az --delete \
	  --exclude '.git' --exclude '.env' --exclude '.venv' --exclude 'node_modules' \
	  --exclude 'frontend' --exclude '__pycache__' --exclude 'docs/reference' \
	  ./ $(VM_HOST):$(VM_DIR)/
	ssh $(VM_HOST) 'cd $(VM_DIR) && docker compose --profile prod up -d --build'

reset: ## Delete the FalkorDB data volume and restart an empty database (then run make load)
	docker compose down -v
	docker compose up -d falkordb
