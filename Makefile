# Load environment variables from .env file
include .env
export

# Define a variable for GPU detection logic
define detect_gpu
	if [ -n "$(GPU_TYPE)" ]; then \
		echo "Using specified GPU_TYPE: $(GPU_TYPE)"; \
		if [ "$(GPU_TYPE)" = "ROCM" ]; then \
			echo "docker-compose-rocm.yaml"; \
		else \
			echo "docker-compose-nvidia.yaml"; \
		fi; \
	elif command -v nvidia-smi > /dev/null 2>&1; then \
		echo "NVIDIA GPU detected"; \
		echo "docker-compose-nvidia.yaml"; \
	elif command -v rocminfo > /dev/null 2>&1; then \
		echo "AMD GPU detected"; \
		echo "docker-compose-rocm.yaml"; \
	else \
		echo "No GPU detected, defaulting to NVIDIA"; \
		echo "docker-compose-nvidia.yaml"; \
	fi
endef

.PHONY: help docker-runpod docker-local docker-nvidia docker-rocm docker-local-start

help:
	@echo "Available targets:"
	@echo "  docker-runpod        Build and push RunPod Docker image"
	@echo "  docker-local         Auto-detect GPU type and build appropriate Docker image"
	@echo "  docker-nvidia        Build Docker image for NVIDIA GPUs"
	@echo "  docker-rocm          Build Docker image for AMD ROCm GPUs"
	@echo "  docker-local-start   Start local Docker service based on detected GPU type"
	@echo "  help                 Show this help message."

# Build and push the RunPod Docker image
docker-runpod:
	@echo "Building RunPod Docker image: ${DOCKER_HUB_REPO}:runpod"
	docker build -f deployment/Dockerfile.runpod -t ${DOCKER_HUB_REPO}:runpod .
	@echo "Pushing RunPod Docker image to Docker Hub"
	docker push ${DOCKER_HUB_REPO}:runpod

# Auto-detect GPU type and build appropriate Docker image
docker-local:
	@COMPOSE_FILE=$$($(detect_gpu) | tail -n1); \
	case "$$COMPOSE_FILE" in \
	    *rocm*) $(MAKE) docker-rocm ;; \
	    *) $(MAKE) docker-nvidia ;; \
	esac

# Start local Docker service based on GPU type
docker-local-start: docker-local
	@COMPOSE_FILE=$$($(detect_gpu) | tail -n1); \
	echo "Starting with $$COMPOSE_FILE"; \
	docker-compose -f $$COMPOSE_FILE down; \
	docker-compose -f $$COMPOSE_FILE up

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
