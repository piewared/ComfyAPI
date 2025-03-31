#!/bin/bash
# docker_entrypoint.sh

# Create a container-specific directory for markers
MARKER_DIR="/app/ComfyUI"
mkdir -p "$MARKER_DIR"

# Define marker file path - now in container's filesystem, not the mounted volume
MARKER_FILE="${MARKER_DIR}/.dependencies_installed"

# Function to calculate a hash of the custom nodes directories and requirements
calculate_custom_nodes_hash() {
  # Create a string containing directory structure and requirements.txt content
  find /app/comfyui_workspace/custom_nodes -type f -name "requirements.txt" -exec cat {} \; 2>/dev/null |
  sort | md5sum | awk '{print $1}'
}

# Get the current hash of custom_nodes
CURRENT_HASH=$(calculate_custom_nodes_hash)

# Check if marker file exists and compare hashes
NEEDS_INSTALL=true
if [ -f "$MARKER_FILE" ]; then
  STORED_HASH=$(cat "$MARKER_FILE")
  if [ "$CURRENT_HASH" == "$STORED_HASH" ]; then
    echo "Dependencies previously installed and custom_nodes unchanged. Skipping installation."
    NEEDS_INSTALL=false
  else
    echo "Custom nodes have changed. Reinstalling dependencies..."
  fi
fi

if [ "$NEEDS_INSTALL" = true ]; then
  echo "Installing custom node dependencies..."

  # Ensure the workspace directory exists
  mkdir -p /app/comfyui_workspace/custom_nodes

  # Run the function to install custom node dependencies
  python -c "import asyncio; import sys; sys.path.append('/app/ComfyAPI'); from src.comfyui.comfyui_manager import ensure_node_reqs; asyncio.run(ensure_node_reqs())"

  # Store the current hash in the marker file
  echo "$CURRENT_HASH" > "$MARKER_FILE"
  echo "Custom node dependencies installation completed."
fi

# Execute the original command (CMD)
exec "$@"