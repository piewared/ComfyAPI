# Load environment variables from .env file
include .env
export

.PHONY: help docker-runpod docker-local docker-nvidia docker-rocm docker-local-start

help:
	@echo "Available targets:"
	@echo "  build-docker-runpod   Build and push RunPod Docker image"
	@echo "  docker-local          Auto-detect GPU type and build appropriate Docker image"
	@echo "  docker-nvidia         Build Docker image for NVIDIA GPUs"
	@echo "  docker-rocm           Build Docker image for AMD ROCm GPUs"
	@echo "  docker-local-start    Start local Docker service based on detected GPU type"
	@echo "  help                  Show this help message"

# Build and push the RunPod Docker image
docker-runpod:
	@echo "Building RunPod Docker image: ${DOCKER_HUB_REPO}:runpod"
	docker build -f deployment/Dockerfile.runpod -t ${DOCKER_HUB_REPO}:runpod .
	@echo "Pushing RunPod Docker image to Docker Hub"
	docker push ${DOCKER_HUB_REPO}:runpod

# Auto-detect GPU type and build appropriate Docker image
docker-local:
	@if [ ! -z "$(GPU_TYPE)" ]; then \
		echo "Using specified GPU_TYPE: $(GPU_TYPE)"; \
		if [ "$(GPU_TYPE)" = "ROCM" ]; then \
			$(MAKE) docker-rocm; \
		else \
			$(MAKE) docker-nvidia; \
		fi; \
	elif command -v nvidia-smi > /dev/null 2>&1; then \
		echo "NVIDIA GPU detected, building with CUDA..."; \
		$(MAKE) docker-nvidia; \
	elif command -v rocminfo > /dev/null 2>&1; then \
		echo "AMD GPU detected, building with ROCm..."; \
		$(MAKE) docker-rocm; \
	else \
		echo "No GPU detected, defaulting to NVIDIA build..."; \
		$(MAKE) docker-nvidia; \
	fi

# Start local Docker service based on GPU type
docker-local-start: docker-local
	@if [ ! -z "$(GPU_TYPE)" ]; then \
		echo "Using specified GPU_TYPE: $(GPU_TYPE)"; \
		if [ "$(GPU_TYPE)" = "ROCM" ]; then \
		    docker compose -f docker-compose-rocm.yaml down; \
			docker compose -f docker-compose-rocm.yaml up; \
		else \
		    docker compose -f docker-compose-nvidia.yaml down; \
			docker compose -f docker-compose-nvidia.yaml up; \
		fi; \
	elif command -v nvidia-smi > /dev/null 2>&1; then \
		echo "NVIDIA GPU detected, starting with CUDA..."; \
		docker compose -f docker-compose-nvidia.yaml down; \
		docker compose -f docker-compose-nvidia.yaml up; \
	elif command -v rocminfo > /dev/null 2>&1; then \
		echo "AMD GPU detected, starting with ROCm..."; \
		docker compose -f docker-compose-rocm.yaml down; \
		docker compose -f docker-compose-rocm.yaml up; \
	else \
		echo "No GPU detected, defaulting to NVIDIA..."; \
		docker compose -f docker-compose-nvidia.yaml down; \
		docker compose -f docker-compose-nvidia.yaml up; \
	fi

# Build NVIDIA-specific Docker image
docker-nvidia:
	@echo "Building Docker image for NVIDIA: ${DOCKER_HUB_REPO}:nvidia"
	docker-compose -f docker-compose-nvidia.yaml build
	docker tag comfyapi-nvidia ${DOCKER_HUB_REPO}:nvidia

# Build ROCm-specific Docker image
docker-rocm:
	@echo "Building Docker image for ROCm: ${DOCKER_HUB_REPO}:rocm"
	docker-compose -f docker-compose-rocm.yaml build
	docker tag comfyapi-rocm ${DOCKER_HUB_REPO}:rocm