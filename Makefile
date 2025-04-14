# Load environment variables from .env file
include .env
export

.PHONY: help build-docker-runpod build-docker build-docker-dev

help:
	@echo "Available targets:"
	@echo "  build-docker-runpod   Build and push RunPod Docker image"
	@echo "  build-docker          Build standard Docker image"
	@echo "  build-docker-dev      Build development Docker image"
	@echo "  help                  Show this help message"

# Build and push the RunPod Docker image
docker-runpod:
	@echo "Building RunPod Docker image: ${DOCKER_HUB_REPO}:runpod"
	docker build -f deployment/Dockerfile.runpod -t ${DOCKER_HUB_REPO}:runpod .
	@echo "Pushing RunPod Docker image to Docker Hub"
	docker push ${DOCKER_HUB_REPO}:runpod

# Build standard Docker image (without pushing)
docker:
	@echo "Building standard Docker image: ${DOCKER_HUB_REPO}:latest"
	docker build -f deployment/Dockerfile.local -t ${DOCKER_HUB_REPO}:latest .

# Build development Docker image (without pushing)
docker-dev:
	@echo "Building development Docker image: ${DOCKER_HUB_REPO}:dev"
	docker build -f deployment/Dockerfile.dev -t ${DOCKER_HUB_REPO}:dev .