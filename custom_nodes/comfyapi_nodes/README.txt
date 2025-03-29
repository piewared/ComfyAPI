# ComfyAPI Custom Nodes for ComfyAPI

This package contains the custom nodes necessary to create workflows compatible with ComfyAPI

## Installation

Copy this entire directory (`comfyapi_nodes`) to the `custom_nodes` folder of your ComfyUI installation:

```bash
cp -r comfyapi_nodes /path/to/ComfyUI/custom_nodes/
```

## Available Nodes

Once installed, you'll have access to:

- **External Image Input (ComfyAPI)** - Takes an image URL to load images from external sources
- **Image Websocket Output (ComfyAPI)** - Sends generated images to connected clients via WebSockets

## How to Use

1. **In ComfyUI:** Create your workflow using standard ComfyUI nodes
2. **Add Input Nodes:** Use "External Image Input" nodes where you need to receive images from external applications
3. **Add Output Nodes:** Use "Image Websocket Output" nodes to send generated images back to connected clients
4. **Export Your Workflow as API:**
    - Click on the "Workflow" button in the ComfyUI toolbar
    - Select "Export (API)" from the menu
    - Save the exported JSON file to the "workflows" folder of your ComfyUI installation (usually under `ComfyUI/user/default/workflows`)
5. **Done** ComfyAPI will automatically detect the new workflow and make it available through the REST API and WebSocket server

## Connection Details

When using these nodes in a workflow:

1. ComfyAPI automatically analyzes your workflow to determine required inputs
2. External applications can queue workflow execution via the `/workflows/{workflow_id}/queue` endpoint
3. Results are streamed back in real-time through WebSockets

## Requirements

- ComfyUI (latest version recommended)
- Python 3.9+
- Pillow
- Requests

## Troubleshooting

- If nodes don't appear in ComfyUI, restart ComfyUI after installation
- Check ComfyUI console/logs for any import or initialization errors

For detailed API documentation, refer to the main ComfyAPI project README.