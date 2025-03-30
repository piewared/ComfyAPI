FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies (git for ComfyUI, ffmpeg for video processing)
RUN apt-get update && \
    apt-get install -y git ffmpeg libsm6 libxext6 wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Clone ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# Install ComfyUI dependencies in a virtual environment
# Install PyTorch - check for GPU_TYPE to determine which version to install
ARG GPU_TYPE=CUDA
WORKDIR /app/ComfyUI
RUN python -m venv .venv && \
    . .venv/bin/activate && \
    if [ "$GPU_TYPE" = "ROCM" ]; then \
        pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2.4; \
    else \
        pip install --no-cache-dir torch torchvision torchaudio; \
    fi && \
    pip install --no-cache-dir -r requirements.txt && \
    deactivate

# Copy ComfyAPI custom nodes to ComfyUI
COPY ./custom_nodes/comfyapi_nodes /app/ComfyUI/custom_nodes/comfyapi_nodes

# Return to app directory and copy ComfyAPI code
WORKDIR /app/ComfyAPI
COPY . /app/ComfyAPI

# Install ComfyAPI dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV COMFYUI_BASE_PATH=/app/ComfyUI
ENV PYTHONPATH=/app/ComfyAPI

# Create directory for workflows
RUN mkdir -p /app/ComfyAPI/workflows

# Expose port for FastAPI
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:8000/ || exit 1

# Command to run the application
CMD ["uvicorn", "src.api.app:app", "--host", "127.0.0.1", "--port", "8000"]