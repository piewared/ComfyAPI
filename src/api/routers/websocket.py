from fastapi import APIRouter, Depends
from starlette.websockets import WebSocket

from src.api.auth import validate_ws_api_key, get_client_ip
from src.comfyui.connection_manager import get_connection_manager, ConnectionManager

router = APIRouter(
    prefix="/ws",
    tags=["ws"],
    responses={404: {"description": "Not found"}},
)


@router.websocket("/register")
async def ws_register(websocket: WebSocket, client_manager: ConnectionManager = Depends(get_connection_manager),
                      ip_address: str = Depends(get_client_ip)):
    """
    Register a new websocket connection.
    :param ip_address:
    :param websocket:
    :param client_manager:
    :return:
    """
    # Delegate connection handling to the connection manager.
    connection_id = await client_manager.accept_client_connection(websocket)
    await client_manager.handle_client_connection(connection_id)
