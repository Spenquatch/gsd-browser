.PHONY: dev lint test smoke diagnose docker-build docker-run

UV ?= uv

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

diagnose:
	./scripts/diagnose.sh

docker-build:
	docker build -t mcp-template:dev -f docker/Dockerfile .

docker-run:
	docker run --rm -e ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} mcp-template:dev
