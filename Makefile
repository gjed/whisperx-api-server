.PHONY: help build-cpu build-cuda up-cpu up-cuda down logs logs-follow \
        shell-cpu shell-cuda test health install-cpu install-cuda run clean \
        venv venv-cpu venv-cuda clean-venv

# Configuration
# Requires Python 3.10-3.12 (PyTorch doesn't support 3.13+ yet)
PYTHON ?= $(shell command -v python3.12 || command -v python3.11 || command -v python3.10 || echo python3)
VENV_DIR ?= .venv
VENV_BIN = $(VENV_DIR)/bin
VENV_PYTHON = $(VENV_BIN)/python
VENV_PIP = $(VENV_BIN)/pip
VENV_UVICORN = $(VENV_BIN)/uvicorn

# Default target
help:
	@echo "WhisperX API Server - Available Commands"
	@echo ""
	@echo "Docker Commands (Recommended):"
	@echo "  make build-cpu      Build CPU Docker image"
	@echo "  make build-cuda     Build CUDA/GPU Docker image"
	@echo "  make up-cpu         Start CPU server (detached)"
	@echo "  make up-cuda        Start CUDA/GPU server (detached)"
	@echo "  make up-cpu-fg      Start CPU server (foreground)"
	@echo "  make up-cuda-fg     Start CUDA/GPU server (foreground)"
	@echo "  make down           Stop all services"
	@echo "  make logs           Show logs"
	@echo "  make logs-follow    Follow logs"
	@echo "  make shell-cpu      Open shell in CPU container"
	@echo "  make shell-cuda     Open shell in CUDA container"
	@echo ""
	@echo "Local Development:"
	@echo "  make venv           Create virtual environment"
	@echo "  make venv-cpu       Create venv + install CPU deps"
	@echo "  make venv-cuda      Create venv + install CUDA deps"
	@echo "  make install-cpu    Install CPU dependencies (in active venv)"
	@echo "  make install-cuda   Install CUDA dependencies (in active venv)"
	@echo "  make run            Run server locally (uvicorn)"
	@echo "  make run-reload     Run server with auto-reload"
	@echo ""
	@echo "Testing:"
	@echo "  make health         Check server health"
	@echo "  make test-transcribe FILE=<path>  Test transcription"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove containers and volumes"
	@echo "  make clean-venv     Remove virtual environment"
	@echo "  make clean-all      Remove everything"
	@echo ""
	@echo "Note: For local dev, either:"
	@echo "  1. Run 'make venv-cpu' or 'make venv-cuda' first, then 'make run'"
	@echo "  2. Or activate venv manually: source .venv/bin/activate"

# =============================================================================
# Docker Commands
# =============================================================================

build-cpu:
	docker compose build whisperx-api-server-cpu

build-cuda:
	docker compose build whisperx-api-server-cuda

up-cpu:
	docker compose up -d whisperx-api-server-cpu

up-cuda:
	docker compose up -d whisperx-api-server-cuda

up-cpu-fg:
	docker compose up whisperx-api-server-cpu

up-cuda-fg:
	docker compose up whisperx-api-server-cuda

down:
	docker compose down

logs:
	docker compose logs

logs-follow:
	docker compose logs -f

shell-cpu:
	docker compose exec whisperx-api-server-cpu /bin/bash

shell-cuda:
	docker compose exec whisperx-api-server-cuda /bin/bash

# =============================================================================
# Virtual Environment
# =============================================================================

$(VENV_DIR):
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PIP) install --upgrade pip

venv: $(VENV_DIR)
	@echo "Virtual environment created at $(VENV_DIR)"
	@echo "Activate with: source $(VENV_DIR)/bin/activate"

venv-cpu: $(VENV_DIR)
	$(VENV_PIP) install -r requirements-cpu.txt
	$(VENV_PIP) install -c constraints.txt -r requirements.txt
	$(VENV_PIP) install -e .
	@echo ""
	@echo "CPU environment ready! Run 'make run' to start the server."

venv-cuda: $(VENV_DIR)
	$(VENV_PIP) install -r requirements-cuda.txt
	$(VENV_PIP) install -c constraints.txt -r requirements.txt
	$(VENV_PIP) install -e .
	@echo ""
	@echo "CUDA environment ready! Run 'make run' to start the server."

# =============================================================================
# Local Development
# =============================================================================

install-cpu:
	pip install -r requirements-cpu.txt
	pip install -c constraints.txt -r requirements.txt
	pip install -e .

install-cuda:
	pip install -r requirements-cuda.txt
	pip install -c constraints.txt -r requirements.txt
	pip install -e .

run: $(VENV_DIR)
	$(VENV_UVICORN) --factory whisperx_api_server.main:create_app --host 0.0.0.0 --port 8000

run-reload: $(VENV_DIR)
	$(VENV_UVICORN) --factory whisperx_api_server.main:create_app --host 0.0.0.0 --port 8000 --reload

# =============================================================================
# Testing
# =============================================================================

health:
	@curl -s http://localhost:8000/healthcheck && echo "" || echo "Server not running"

test-transcribe:
ifndef FILE
	@echo "Usage: make test-transcribe FILE=<path-to-audio-file>"
	@echo "Example: make test-transcribe FILE=./audio.mp3"
else
	curl -X POST http://localhost:8000/v1/audio/transcriptions \
		-F "file=@$(FILE)" \
		-F "model=large-v3"
endif

# =============================================================================
# Cleanup
# =============================================================================

clean:
	docker compose down -v --remove-orphans

clean-venv:
	rm -rf $(VENV_DIR)

clean-all: clean clean-venv
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
