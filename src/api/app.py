import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
import uvicorn

from src.api.auth import validate_api_key
from src.api.routers import workflows, lifecycle, websocket
from src.comfyui.comfyui_manager import get_manager
from src.comfyui.connection_manager import initialize_connection_manager
from src.config import get_app_settings

from src.utils.logger_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize the ComfyUI manager.
    comfyui_manager = get_manager()
    await comfyui_manager.start()
    # Initialize the connection manager.
    connection_manager = initialize_connection_manager(comfyui_manager)

    # Start task to clean up idle connections.
    asyncio.create_task(connection_manager.run_connection_cleanup())
    yield
    # Clean up the ML models and release the resources
    await comfyui_manager.stop()
    #await connection_manager.close_all_connections()

app = FastAPI(lifespan=lifespan)


app.include_router(workflows.router, dependencies=[Depends(validate_api_key)])
app.include_router(lifecycle.router, dependencies=[Depends(validate_api_key)])
app.include_router(websocket.router)

configure_logging()


@app.get("/")
async def root():
    return {"message": "Hello Bigger Applications!"}


if __name__ == "__main__":
    app_settings = get_app_settings()
    uvicorn.run(app, host=app_settings.listen_address, port=app_settings.listen_port)
