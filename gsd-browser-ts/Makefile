.PHONY: dev lint test smoke diagnose docker-build docker-run

PM ?= npm

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
