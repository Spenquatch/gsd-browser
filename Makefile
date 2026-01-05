.PHONY: help py-% ts-%

.DEFAULT_GOAL := help

help:
	@echo ""
	@echo "Repo targets (run from repo root):"
	@echo ""
	@echo "  Python (gsd-browser/)"
	@echo "    make py-help        Show python subproject targets"
	@echo "    make py-dev         Create .venv and install deps"
	@echo "    make py-lint        Run Ruff lint (requires py-dev)"
	@echo "    make py-test        Run Pytest (requires py-dev)"
	@echo "    make py-smoke       Run python smoke test script"
	@echo "    make py-sanity-real Run real-world sanity harness (requires py-dev)"
	@echo "    make py-diagnose    Run python diagnostics script"
	@echo ""
	@echo "  TypeScript (gsd-browser-ts/)"
	@echo "    make ts-help        Show TS subproject targets"
	@echo "    make ts-install     Install npm deps"
	@echo "    make ts-dev         Run TS dev server"
	@echo "    make ts-lint        Run ESLint"
	@echo "    make ts-test        Run Vitest"
	@echo "    make ts-smoke       Run TS smoke test script"
	@echo "    make ts-diagnose    Run TS diagnostics script"
	@echo ""
	@echo "Notes:"
	@echo "  - Most commands run inside the corresponding subproject directory."
	@echo "  - Example: make py-test"

py-%:
	@$(MAKE) -C gsd-browser $*

ts-%:
	@$(MAKE) -C gsd-browser-ts $*
