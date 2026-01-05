.PHONY: help dev lint test smoke diagnose sanity-real docker-build docker-run

UV ?= uv

help:
	@echo ""
	@echo "gsd-browser (Python) targets:"
	@echo "  make dev         Create .venv and install deps"
	@echo "  make lint        Run Ruff lint (requires dev)"
	@echo "  make test        Run Pytest (requires dev)"
	@echo "  make smoke       Run smoke test script"
	@echo "  make sanity-real Run real-world sanity harness (requires dev)"
	@echo "  make diagnose    Run diagnostics script"
	@echo "  make docker-build Build docker image"
	@echo "  make docker-run   Run docker image"

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
	@if [ -x .venv/bin/python ]; then \
		. .venv/bin/activate && python ./scripts/real_world_sanity.py; \
	else \
		echo "Run 'make dev' first to create .venv"; \
		exit 1; \
	fi

diagnose:
	./scripts/diagnose.sh

docker-build:
	docker build -t gsd-browser:dev -f docker/Dockerfile .

docker-run:
	docker run --rm -e ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} gsd-browser:dev
