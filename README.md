# ComfyAPI 🚀

A friendly FastAPI-based service that provides REST API and WebSocket interfaces to ComfyUI, making it easy to run AI image generation workflows remotely.

## What's This All About? 🤔

ComfyAPI sits between your applications and ComfyUI, handling the communication details so you can focus on creating images. It manages process lifecycles and connections behind the scenes.

ComfyUI has powerful capabilities, but its communication protocols can be complex. This project bridges that gap by providing a simple standardize REST interface that applications can use. Whether you're working with web apps, mobile services, or automation scripts, ComfyAPI simplifies the integration.

### How It Works 🔌

ComfyAPI connects your applications to ComfyUI through several components:

- **API Layer** - Offers a structured REST interface for applications
- **Protocol Bridge** - Handles conversion between HTTP requests and ComfyUI's WebSocket messages
- **Connection Management** - Maintains the websocket connections with proper lifecycle handling
- **Custom Nodes** - Extends ComfyUI with specialized input/output nodes for API integration
- **Input Processing** - Validates and formats inputs for ComfyUI workflows
- **Output Streaming** - Delivers results back through websockets in real-time

Built on FastAPI's asynchronous foundation and equipped with specialized connection managers, the system can handle numerous concurrent requests, making it suitable for multi-user environments or high-volume processing scenarios.  This abstraction lets you work with ComfyUI through straightforward API calls without worrying about its internal implementation details.


## Features ✨

- **REST API** - Structured endpoints for workflow execution
- **WebSocket Interface** - Real-time updates during image generation
- **Connection Handling** - Automatic management of client-backend connections
- **Workflow Analysis** - Automatic extraction of inputs and outputs from workflows
- **API Key Auth** - Simple security for your endpoints
- **Auto-Cleanup** - Background handling of idle connections

## Project Structure 📦

```
├── src/
│   ├── api/                 # API endpoints and routers
│   ├── comfyui/             # ComfyUI integration code
│   ├── data/                # Data models and schemas
│   └── utils/               # Helper utilities
├── workflows/               # Example workflow definitions
├── custom_nodes/            # ComfyUI custom input/output nodes
├── .env                     # Configuration settings
└── .env.sample              # Template configuration file
```

## Before You Dive In 🏊

- Python 3.9+ 
- ComfyUI installed and ready to go
- Access to wherever ComfyUI lives on your system

## Getting Started 🚀

1. Grab the code:
   ```bash
   git clone https://github.com/your-username/comfyapi.git
   cd comfyapi
   ```

2. Set up your Python playground:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Get the ingredients:
   ```bash
   pip install -r requirements.txt
   ```

4. Create your secret recipe:
   ```bash
   cp .env.sample .env
   ```

5. Set the path to your ComfyUI installation and your API key in the `.env` file:
   ```
   COMFYUI_BASE_PATH=/path/to/ComfyUI
   APP_API_KEY=your_secure_api_key
   ```
   The API key is used to authenticate requests to the API. It should be kept secret and only shared with trusted  applications.

## Fire It Up! 🔥

```bash
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

## How to Use This Thing 🛠️

### Creating ComfyAPI Workflows in ComfyUI ###
1. **Install the ComfyUI custom nodes**
    - Copy the custom_nodes/ComfyAPI folder to your ComfyUI installation's custom_nodes directory
2. **Create a workflow in ComfyUI**:
   - Add nodes and connections as usual to build your image generation process
   - Use the ComfyAPI input and output nodes to define your workflow's inputs and outputs

### Knocking on the Door (Authentication)

Don't forget your unique API key! Add this to your request headers:

```
X-API-Key: APP_API_KEY
```

### Playing with Workflows

1. **See what workflows are available**:
   ```
   GET /workflows/
   ```

2. **Look under the hood of a workflow to get its requested inputs**:
   ```
   GET /workflows/{workflow_id}
   ```

3. **Get yourself a websocket**:
    - Use your favorite websocket client to connect to `/ws/register` with your API key
    - You'll get a response containing a connection ID to use in the next step:
    ```
    {"websocket_cid":"7e51a24f2cbf4873b205a414aab33897"}
    ```

4. **Populate the input nodes and make the magic happen**:
   ```
   POST /workflows/{workflow_id}/queue
   ```
   With this in the body:
   ```json
   {
     "websocket_cid": "your_websocket_cid",
     "inputs": [
       {
         "node_id": "node_1",
         "value": "https://example.com/image.jpg"
       }
     ]
   }
   ```
5. **Sit back and enjoy the show**:
   Through the websocket, you'll get progress updates and the final masterpiece when it's ready!

## Under the Hood 🔧

### The Connection Conductor

Our `ConnectionManager` is like an air traffic controller for websockets - keeping everything flowing smoothly between clients and ComfyUI.

### The ComfyUI Wrangler

The `ComfyUIManager` is the boss of ComfyUI - it starts it up, sends it work, and makes sure it's behaving properly.

### The Workflow Detective

Our analysis tools peek into workflows to figure out what makes them tick - inputs, outputs, and how everything connects.

## Join the Fun! 🤝

1. Fork it!
2. Branch it!
3. Change it!
4. Pull request it!

## Disclaimer ⚠️

This software is provided "as is", without warranty of any kind, express or implied. The authors or copyright holders shall not be liable for any claim, damages or other liability arising from the use of the software.

## Fine Print

[MIT License](LICENSE) - Go wild, just remember where you got it from!