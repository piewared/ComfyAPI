import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response, FileResponse
from io import BytesIO
from pathlib import Path
from typing import Dict

from src.comfyui.comfyui_workspace import (
    backup_workspace,
    set_workspace,
    restore_workspace,
    delete_workspace,
    get_workspace,
    ensure_workspace_initialized
)

router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def download_workspace() -> Response:
    """
    Download the current workspace as a tar archive.
    """
    try:
        workspace_bytes = await get_workspace()
        return Response(
            content=workspace_bytes,
            media_type="application/gzip",
            headers={"Content-Disposition": "attachment; filename=workspace.tar.gz"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download workspace: {str(e)}")


@router.put("/")
async def upload_workspace(file: UploadFile = File(...)) -> Dict[str, str]:
    """
    Upload and set a new workspace from a tar archive.
    """
    try:
        content = await file.read()
        file_obj = BytesIO(content)
        await set_workspace(file_obj)
        return {"status": "success", "message": "Workspace uploaded and set successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set workspace: {str(e)}")


@router.post("/backup")
async def create_backup() -> Dict[str, str]:
    """
    Create a backup of the current workspace.
    """
    try:
        backup_path = await backup_workspace()
        return {"status": "success", "backup_path": str(backup_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to backup workspace: {str(e)}")


@router.post("/restore")
async def restore_from_backup() -> Dict[str, str]:
    """
    Restore workspace from the most recent backup.
    """
    try:
        await restore_workspace()
        return {"status": "success", "message": "Workspace restored successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore workspace: {str(e)}")


@router.delete("/")
async def remove_workspace() -> Dict[str, str]:
    """
    Delete all files in the current workspace.
    """
    try:
        await delete_workspace()
        await ensure_workspace_initialized()
        return {"status": "success", "message": "Workspace deleted and reinitialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete workspace: {str(e)}")