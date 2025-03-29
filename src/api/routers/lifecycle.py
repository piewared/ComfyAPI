from fastapi import APIRouter, Depends
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.comfyui.comfyui_manager import ComfyUIManager, ComfyUIStatus, get_manager

router = APIRouter(
    prefix="/lifecycle",
    tags=["lifecycle"],
    responses={404: {"description": "Not found"}},
)


@router.post("/start")
async def start_comfyui(comfyui_manager: ComfyUIManager = Depends(get_manager)):
    status_enum = await comfyui_manager.start()
    http_code = 200 if status_enum == ComfyUIStatus.STARTING else 500
    return JSONResponse(content={"status": status_enum.value}, status_code=http_code)

@router.post("/stop")
async def stop_comfyui(comfyui_manager: ComfyUIManager = Depends(get_manager)):
    status_enum = await comfyui_manager.stop()
    http_code = 200 if status_enum == ComfyUIStatus.NOT_RUNNING else 500
    return JSONResponse(content={"status": status_enum.value}, status_code=http_code)

@router.get("/status")
async def status_comfyui(comfyui_manager: ComfyUIManager = Depends(get_manager)):
    result = await comfyui_manager.status()
    return result