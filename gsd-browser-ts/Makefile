.PHONY: help install dev lint test smoke diagnose docker-build docker-run

PM ?= npm

help:
	@echo ""
	@echo "gsd-browser-ts (TypeScript) targets:"
	@echo "  make install     Install npm deps"
	@echo "  make dev         Run dev server (installs deps first)"
	@echo "  make lint        Run ESLint"
	@echo "  make test        Run Vitest"
	@echo "  make smoke       Run smoke test script"
	@echo "  make diagnose    Run diagnostics script"
	@echo "  make docker-build Build docker image"
	@echo "  make docker-run   Run docker image"

install:
	$(PM) install

dev: install
	$(PM) run dev

lint:
	$(PM) run lint

test:
	$(PM) run test

smoke:
	./scripts/smoke-test.sh

diagnose:
	./scripts/diagnose.sh

docker-build:
	docker build -t gsd-browser-ts:dev -f docker/Dockerfile .

docker-run:
	docker run --rm -e ANTHROPIC_API_KEY=$${ANTHROPIC_API_KEY} gsd-browser-ts:dev
