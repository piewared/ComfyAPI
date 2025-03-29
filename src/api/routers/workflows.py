import json
import uuid

from fastapi import APIRouter, Depends
from starlette.exceptions import HTTPException

from src.comfyui.comfyui_manager import ComfyUIManager, get_manager, WorkflowTask
from src.comfyui.workflow_analysis import analyze_workflow, WorkflowDescriptor, WorkflowInput, get_workflows, get_workflow_path_by_id
from src.comfyui.connection_manager import ConnectionManager, get_connection_manager

router = APIRouter(
    prefix="/workflows",
    tags=["workflows"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def get_workflow_ids() -> list[str]:
    """
    List all workflows IDs
    :return:
    """
    workflow_ids_to_paths = get_workflows()

    # Return the sorted ids
    return sorted(workflow_ids_to_paths.keys())


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> WorkflowDescriptor:
    """
    Get a detailed description of a workflow by ID.
    :param workflow_id:
    :return:
    """
    try:
        workflow_path = get_workflow_path_by_id(workflow_id)
        workflow_desc = analyze_workflow(workflow_id, workflow_path)
        if not workflow_desc:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")

        return workflow_desc

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found.")

@router.post("/{workflow_id}/queue")
async def queue_workflow(workflow_id: str, websocket_cid: str, inputs: list[WorkflowInput],
                         comfyui_manager: ComfyUIManager = Depends(get_manager),
                         ws_manager: ConnectionManager = Depends(get_connection_manager)) -> dict[str, str]:
    """
    Queue a workflow by ID for execution. A websocket connection ID is required.
    The connection ID must first be retrieved by calling the /ws/register endpoint. This websocket will be used to
    communicate the workflow status as well as the final image output.
    """

    # Check if the websocket connection exists.
    websocket_sid = await ws_manager.get_server_connection_id(websocket_cid)

    if not websocket_sid:
        raise HTTPException(status_code=404, detail=f"Connection {websocket_cid} not found.")

    async def status_callback(wf_status: WorkflowTask):
        await ws_manager.send_client_message(websocket_cid, json.dumps({"type": "workflow_status", "request_id": request_id, "status": wf_status.status}))

    path = get_workflow_path_by_id(workflow_id)
    descriptor = analyze_workflow(workflow_id, path)
    descriptor.inputs = inputs

    # Let's generate a request ID for this workflow. Limit to 24 characters.
    request_id = uuid.uuid4().hex.replace('-', '')[:24]

    await comfyui_manager.run_workflow(websocket_sid, request_id, descriptor, status_callback)

    return {'request_id': request_id}


