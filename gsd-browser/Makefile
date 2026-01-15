.PHONY: help dev lint test smoke diagnose sanity-real prompt-compare docker-build docker-run

UV ?= uv
SANITY_REAL_CONFIRM ?=
SANITY_REAL_ARGS ?=
PROMPT_COMPARE_CONFIRM ?=

help:
	@echo ""
	@echo "gsd (Python) targets:"
	@echo "  make dev           Create .venv and install deps"
	@echo "  make lint          Run Ruff lint (requires dev)"
	@echo "  make test          Run Pytest (requires dev)"
	@echo "  make smoke         Run smoke test script"
	@echo "  make sanity-real   Run real-world sanity harness (manual; requires credentials + internet)"
	@echo "  make prompt-compare Compare extended vs override-enhanced prompts (manual; requires credentials)"
	@echo "  make diagnose      Run diagnostics script"
	@echo "  make docker-build  Build docker image"
	@echo "  make docker-run    Run docker image"

dev:
	@if command -v $(UV) >/dev/null 2>&1; then \
		$(UV) venv --python 3.11 --allow-existing .venv; \
		$(UV) pip install --python .venv -e ".[dev]"; \
	else \
		python3 -m venv .venv; \
		. .venv/bin/activate && python -m ensurepip --upgrade && pip install --upgrade pip && pip install -e ".[dev]"; \
	fi

lint:
	@if [ -x .venv/bin/ruff ]; then \
		. .venv/bin/activate && ruff check; \
	else \
		echo "Run 'make dev' first to create .venv"; \
		exit 1; \
	fi

test:
	@if [ -x .venv/bin/pytest ]; then \
		. .venv/bin/activate && pytest; \
	else \
		echo "Run 'make dev' first to create .venv"; \
		exit 1; \
	fi

smoke:
	./scripts/smoke-test.sh

sanity-real:
	@if [ "$(SANITY_REAL_CONFIRM)" != "1" ]; then \
		echo "Refusing to run: this harness hits external websites and requires credentials + internet."; \
		echo "To run anyway: SANITY_REAL_CONFIRM=1 make sanity-real"; \
		echo "Optional args: SANITY_REAL_ARGS='--scenario <id> --out <dir>'"; \
		exit 2; \
	fi
	@if [ -x .venv/bin/python ]; then \
		GSD_MODEL=$${GSD_MODEL:-claude-sonnet-4-5} \
		GSD_WEB_EVAL_STEP_TIMEOUT_S=$${GSD_WEB_EVAL_STEP_TIMEOUT_S:-30.0} \
		GSD_WEB_EVAL_BUDGET_S=$${GSD_WEB_EVAL_BUDGET_S:-120.0} \
		. .venv/bin/activate && python ./scripts/real_world_sanity.py $(SANITY_REAL_ARGS); \
	else \
		echo "Run 'make dev' first to create .venv"; \
		exit 1; \
	fi

prompt-compare:
	@if [ "$(PROMPT_COMPARE_CONFIRM)" != "1" ]; then \
		echo "Prompt Comparison Harness: Extended vs Override-Enhanced"; \
		echo ""; \
		echo "This harness:"; \
		echo "  - Runs 3 scenarios (simple, medium, high complexity) twice each"; \
		echo "  - First with extended prompt (current A1), then with override-enhanced"; \
		echo "  - Uses 4x timeout lengths (60s step, 240s budget for Haiku)"; \
		echo "  - Default model: claude-haiku-4-5"; \
		echo ""; \
		echo "To run: PROMPT_COMPARE_CONFIRM=1 make prompt-compare"; \
		echo ""; \
		echo "Options:"; \
		echo "  GSD_MODEL=<model>        Override model (default: claude-haiku-4-5)"; \
		echo "  --step-timeout=<seconds>         Override step timeout (default: 60.0)"; \
		echo "  --budget=<seconds>               Override budget timeout (default: 240.0)"; \
		exit 2; \
	fi
	@if [ -x .venv/bin/python ]; then \
		GSD_MODEL=$${GSD_MODEL:-claude-haiku-4-5} \
		. .venv/bin/activate && python ./scripts/prompt_comparison_harness.py; \
	else \
		echo "Run 'make dev' first to create .venv"; \
		exit 1; \
	fi

diagnose:
	./scripts/diagnose.sh

docker-build:
	docker build -t gsd:dev -f docker/Dockerfile .

docker-run:
	docker run --rm -e ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} gsd:dev
