# Makefile for local development of dnd-game-master-agent

# Use bash so `set -o pipefail` works — it makes the pytest exit code propagate
# through the `tee` pipe, so `make test`/`make integration` still fail on failures
# even though their output is also written to a log file.
SHELL := /bin/bash

# Test output is tee'd here for post-run analysis (terminal output can scroll the
# stack trace away). These are *.log files and are gitignored.
LOG_DIR := logs

.PHONY: install lint lint-fix playground run test integration smoke-test help

# Default target
help:
	@echo "Available commands:"
	@echo "  make install        Install project dependencies (uv sync)"
	@echo "  make lint           Run linter and type checks"
	@echo "  make lint-fix       Run linter and format code with auto-fixes"
	@echo "  make playground     Start the local ADK web playground"
	@echo "  make run PROMPT=... Run a single prompt through the agent"
	@echo "  make test           Run unit tests (logs to $(LOG_DIR)/make-test.log)"
	@echo "  make integration    Run the graph-workflow integration tests (logs to $(LOG_DIR)/make-integration.log)"
	@echo "  make smoke-test     Run smoke tests for tools and custom routes"

install:
	agents-cli install

lint:
	agents-cli lint

lint-fix:
	agents-cli lint --fix

playground:
	agents-cli playground

local:
	uv run python app/fast_api_app.py

run:
	@if [ -z "$(PROMPT)" ]; then \
		echo "Error: Please specify PROMPT. Example: make run PROMPT=\"start adventure\""; \
		exit 1; \
	fi
	agents-cli run "$(PROMPT)"

test:
	@mkdir -p $(LOG_DIR)
	set -a && . ./app/.env && set +a && set -o pipefail && \
		uv run --extra local pytest tests/unit 2>&1 | tee $(LOG_DIR)/make-test.log

integration:
	@mkdir -p $(LOG_DIR)
	set -a && . ./app/.env && set +a && set -o pipefail && \
		uv run --extra local pytest tests/integration/test_agent.py 2>&1 | tee $(LOG_DIR)/make-integration.log

story-test:
	uv run python scripts/test_story_agent.py

smoke-test:
	uv run python smoke_test.py
