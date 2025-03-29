from typing import Optional

from dotenv import load_dotenv
from fastapi import Security, HTTPException, status, Header, Request
from fastapi.security import APIKeyHeader
from starlette.websockets import WebSocket

from src.config import get_app_settings

api_key_header = APIKeyHeader(name="X-API-Key")
app_settings = get_app_settings()

load_dotenv()

def check_api_key(api_key: str):
    return api_key == app_settings.api_key


async def validate_ws_api_key(token: str = Header(...)):
    return await validate_api_key(token,)


async def validate_api_key(api_key_header: str = Security(api_key_header)):
    if check_api_key(api_key_header):
        return api_key_header
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API key"
    )


def get_websocket_client_ip(ws: WebSocket) -> str:
    client_ip = ws.headers.get("X-Forwarded-For", None)
    if not client_ip and ws.client:
        client_ip = ws.client.host

    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine client IP"
        )

    return client_ip

def get_request_client_ip(request: Request) -> str:
    client_ip = request.headers.get("X-Forwarded-For", None)
    if not client_ip and request.client:
        client_ip = request.client.host

    if not client_ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not determine client IP"
        )

    return client_ip

def get_client_ip(request: Request = None, ws: WebSocket = None) -> str:
    if request:
        return get_request_client_ip(request)
    if ws:
        return get_websocket_client_ip(ws)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Could not determine client IP"
    )