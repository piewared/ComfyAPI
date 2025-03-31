#!/bin/bash
# docker_entrypoint.sh

# Use the container ID (Docker sets HOSTNAME to the container ID)
CONTAINER_ID=${HOSTNAME}

# Define marker file path with the container ID
MARKER_FILE="/app/comfyui_workspace/.dependencies_installed_${CONTAINER_ID}"

# Check if dependencies have already been installed for this container
if [ ! -f "$MARKER_FILE" ]; then
    echo "First run for container ${CONTAINER_ID}: Installing custom node dependencies..."

    # Check if the directory exists
    if [ ! -d "/app/comfyui_workspace" ]; then
        echo "Directory /app/comfyui_workspace does not exist. Exiting."
        exit 1
    fi

    # Run the function to install custom node dependencies
    python -c "import asyncio; import sys; sys.path.append('/app/ComfyAPI'); from src.comfyui.comfyui_manager import ensure_node_reqs; asyncio.run(ensure_node_reqs())"

    # Create marker file to indicate dependencies were installed
    touch "$MARKER_FILE"
    echo "Custom node dependencies installation completed for container: ${CONTAINER_ID}"
else
    echo "Dependencies previously installed for this container. Skipping installation."
fi

# Execute the original command (CMD)
exec "$@"