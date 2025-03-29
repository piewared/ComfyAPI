"""
ConnectionManager Module

This module defines a ConnectionManager class that handles WebSocket connections for both
clients and the ComfyUI backend. It uses TimeoutMap instances to manage connection lifecycles,
proxy messages between clients and the backend, and performs periodic cleanup of idle connections.
"""

import asyncio
import json
import uuid
from typing import Optional, Callable, Awaitable

import websockets
from loguru import logger
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from src.comfyui.comfyui_manager import ComfyUIManager
from src.utils.collections import TimeoutMap

# Type alias for message handlers
MessageHandler = Optional[Callable[[str, str], Awaitable[None]]]


class ConnectionManager:
    """
    Manages WebSocket connections for both clients and the ComfyUI backend server.

    Responsibilities include:
      - Accepting and initializing client connections.
      - Proxying messages between clients and the ComfyUI backend.
      - Handling connection eviction and cleanup.
      - Sending messages to clients and backend servers.
    """

    def __init__(
            self,
            comfyui_manager: ComfyUIManager,
            idle_timeout: int = 60 * 60,
            time_function: Optional[Callable[[], float]] = None,
            connection_close_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ):
        """
        Initialize the ConnectionManager.

        :param comfyui_manager: Instance of ComfyUIManager for backend connections.
        :param idle_timeout: Idle timeout in seconds for connections (default: 1 hour).
        :param time_function: Optional function to retrieve the current time (for TimeoutMap).
        :param connection_close_callback: Optional callback invoked when a connection closes.
        """
        self._comfyui_manager = comfyui_manager

        # List of callbacks to invoke upon connection closure
        self._connection_close_callbacks = [connection_close_callback] if connection_close_callback else []

        # TimeoutMap instances to manage client and server connections and tasks
        self._client_connections = TimeoutMap[WebSocket](idle_timeout, time_function, self._evict_client_callback)
        self._server_connections = TimeoutMap[websockets.ClientConnection](
            idle_timeout, time_function, self._evict_server_callback)
        self._sid_task_map = TimeoutMap[asyncio.Task](idle_timeout=60 * 60, evict_callback=self._task_evict_callback)

        # Mapping between client connection IDs (cid) and server connection IDs (sid)
        self._cid_sid_map: dict[str, str] = {}
        self._sid_cid_map: dict[str, str] = {}

    async def _task_evict_callback(self, sid: str, task: asyncio.Task) -> None:
        """
        Callback executed when a backend task is evicted.

        Cancels the task associated with the provided server connection ID.

        :param sid: Server connection ID.
        :param task: The asyncio Task to cancel.
        """
        logger.debug(f"Cancelling task for {sid}")
        task.cancel()

    async def _evict_client_callback(self, cid: str, ws: WebSocket):
        """
        Callback to handle eviction of a client connection.

        Cleans up the mapping entries, closes the WebSocket if still open,
        and triggers any registered connection close callbacks.

        :param cid: Client connection ID.
        :param ws: The client WebSocket instance.
        """
        logger.debug(f"Closing client connection {cid}.")
        keys = await self._client_connections.keys()
        logger.debug(f"Number of active client connections: {len(keys)}")

        if cid in self._cid_sid_map:
            # Remove corresponding server connection mapping
            sid = self._cid_sid_map.pop(cid)
            self._sid_cid_map.pop(sid)
            await self._server_connections.pop(sid)
            logger.debug(f"Removed connection {cid}:{sid} from all mappings")

        # Close the WebSocket if not already disconnected
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()

        # Invoke any registered connection close callbacks
        if self._connection_close_callbacks:
            for callback in self._connection_close_callbacks:
                await callback(cid)

    async def _evict_server_callback(self, sid: str, ws: websockets.ClientConnection):
        """
        Callback to handle eviction of a server connection.

        Cleans up mapping entries, cancels the associated task, closes the connection if still open,
        and triggers any registered connection close callbacks.

        :param sid: Server connection ID.
        :param ws: The backend's ClientConnection instance.
        """
        logger.debug(f"Closing server connection {sid}.")
        keys = await self._server_connections.keys()
        logger.debug(f"Number of active server connections: {len(keys)}")

        if sid in self._sid_cid_map:
            # Remove corresponding client connection mapping
            cid = self._sid_cid_map.pop(sid)
            self._cid_sid_map.pop(cid)
            await self._client_connections.pop(cid)
            logger.debug(f"Removed connection {cid}:{sid} from mapping.")

        # Cancel the socket reading task
        task = await self._sid_task_map.pop(sid)

        # Close the connection if not already closed
        if ws.state != websockets.protocol.State.CLOSED:
            await ws.close()

        # Invoke any registered connection close callbacks
        if self._connection_close_callbacks:
            for callback in self._connection_close_callbacks:
                await callback(sid)

    async def _accept(self, websocket: WebSocket) -> str:
        """
        Accept a new client WebSocket connection and assign it a unique connection ID.

        :param websocket: The client WebSocket instance.
        :return: The generated unique connection ID.
        """
        await websocket.accept()
        connection_id = str(uuid.uuid4()).replace('-', '')
        await self._client_connections.set(connection_id, websocket)
        return connection_id

    def add_connection_close_callback(self, callback: Callable[[str], Awaitable[None]]):
        """
        Register a callback to be invoked when a connection closes.

        :param callback: A callable that accepts a connection ID.
        """
        self._connection_close_callbacks.append(callback)

    async def disconnect(self, connection_id: str):
        """
        Disconnect a connection by its ID.

        Attempts to remove the connection from client connections first; if not found,
        then from server connections.

        :param connection_id: The connection ID to disconnect.
        """
        ws = await self._client_connections.pop(connection_id)
        if not ws:
            ws = await self._server_connections.pop(connection_id)
            if not ws:
                logger.warning(f"Connection {connection_id} not found.")

    async def send_server_message(self, connection_id: str, message: str | bytes):
        """
        Send a message to a server connection.

        :param connection_id: The server connection ID.
        :param message: The message to send (either str or bytes).
        """
        websocket = await self.get_server_connection(connection_id)
        if websocket:
            await websocket.send(message)
        else:
            logger.warning(f"Connection {connection_id} not found.")

    async def send_client_message(self, connection_id: str, message: str | bytes):
        """
        Send a message to a client connection.

        Updates the activity timestamp and sends the message as text or bytes.

        :param connection_id: The client connection ID.
        :param message: The message to send (str or bytes).
        :raises ValueError: If the message is not a string or bytes.
        """
        websocket = await self.get_client_connection(connection_id)
        if websocket:
            await self._update_activity(connection_id)
            if isinstance(message, str):
                await websocket.send_text(message)
            elif isinstance(message, bytes):
                await websocket.send_bytes(message)
            else:
                raise ValueError("Message must be a string or bytes")
        else:
            logger.warning(f"Connection {connection_id} not found.")

    async def get_client_connection(self, connection_id: str) -> Optional[WebSocket]:
        """
        Retrieve the client WebSocket associated with the given connection ID.

        :param connection_id: The client connection ID.
        :return: The WebSocket instance if found; otherwise, None.
        """
        return await self._client_connections.get(connection_id)

    async def get_server_connection(self, connection_id: str) -> Optional[websockets.ClientConnection]:
        """
        Retrieve the server connection associated with the given connection ID.

        :param connection_id: The server connection ID.
        :return: The ClientConnection instance if found; otherwise, None.
        """
        return await self._server_connections.get(connection_id)

    async def get_client_connection_id(self, sid: str) -> Optional[str]:
        """
        Get the client connection ID corresponding to a server connection ID.

        :param sid: The server connection ID.
        :return: The client connection ID if found; otherwise, None.
        """
        return self._sid_cid_map.get(sid)

    async def get_server_connection_id(self, cid: str) -> Optional[str]:
        """
        Get the server connection ID corresponding to a client connection ID.

        :param cid: The client connection ID.
        :return: The server connection ID if found; otherwise, None.
        """
        return self._cid_sid_map.get(cid)

    async def proxy_comfyui_connection(self, client_websocket: WebSocket) -> str:
        """
        Proxy messages between the client and the ComfyUI backend.

        Establishes a backend connection, sets up message proxying, and handles reconnections
        in case of errors.

        :param client_websocket: The client's WebSocket connection.
        :return: The server connection ID associated with the backend.
        """

        async def connect_to_backend():
            """
            Establish a connection to the backend and start a task for proxying messages
            from the backend to the client.

            :return: A tuple of (server connection ID, backend WebSocket connection).
            """
            sid, backend_ws = await self._comfyui_manager.connect_to_backend()
            await self._server_connections.set(sid, backend_ws)

            logger.debug(f"Starting proxy task between {client_websocket} and {backend_ws}")
            # Start a background task to proxy backend messages to the client.
            t = asyncio.create_task(backend_to_client())
            await self._sid_task_map.set(sid, t)

            return sid, backend_ws

        async def backend_to_client():
            """
            Proxy messages from the backend to the client WebSocket.

            Continuously receives messages from the backend and forwards them to the client.
            In case of an error, attempts to reconnect to the backend.
            """
            nonlocal backend_ws

            while True:
                try:
                    message = await backend_ws.recv()
                    if isinstance(message, bytes):
                        # Skip the first 8 bytes and send the rest as binary data.
                        await client_websocket.send_bytes(message[8:])
                    else:
                        # Currently, text messages are not forwarded.
                        pass
                except Exception as e:
                    logger.error("Error in backend_to_client", e)
                    try:
                        await self.disconnect(sid)
                        await connect_to_backend()
                        logger.info("Reconnected to backend in backend_to_client.")
                    except Exception as re:
                        logger.error("Reconnection failed in backend_to_client: %s", re)
                        await client_websocket.send_text(json.dumps({"error": "Lost connection to backend"}))
                        break

        # Establish connection to the backend and start message proxying.
        sid, backend_ws = await connect_to_backend()
        return sid

    async def accept_client_connection(self, websocket: WebSocket) -> str:
        """
        Accept and initialize a client WebSocket connection.

        Accepts the connection, proxies messages to the backend, sends the assigned connection ID
        to the client, and maintains the mapping between client and server IDs.

        :param websocket: The client WebSocket connection.
        :return: The unique client connection ID.
        """
        # Accept the client connection and generate a unique connection ID.
        connection_id = await self._accept(websocket)

        # Start proxying messages between the client and the ComfyUI backend.
        sid = await self.proxy_comfyui_connection(websocket)

        # Maintain the mapping between client and server connection IDs.
        self._cid_sid_map[connection_id] = sid
        self._sid_cid_map[sid] = connection_id

        try:
            await websocket.send_json({"uuid": connection_id})
        except WebSocketDisconnect:
            logger.debug(f"WebSocket {connection_id} disconnected.")
            await self.disconnect(connection_id)
        except Exception as exc:
            logger.exception(f"Unexpected error on connection {connection_id}: {exc}")

        return connection_id

    async def handle_client_connection(self, connection_id: str):
        """
        Handle incoming messages from a client WebSocket.

        Continuously listens for client messages, updates the activity timestamp,
        logs the message, and forwards it to the backend server.

        :param connection_id: The client connection ID.
        """
        websocket = await self._client_connections.get(connection_id)
        if not websocket:
            logger.warning(f"Connection {connection_id} not found.")
            return

        sid = self._cid_sid_map.get(connection_id)
        if not sid:
            logger.warning(f"Server connection not found for client {connection_id}.")
            return

        try:
            while True:
                message = await websocket.receive_text()
                await self._update_activity(connection_id)
                logger.debug(f"Received message on connection {connection_id}: {message}")
                # Forward the message to the backend server.
                await self.send_server_message(sid, message)
        except WebSocketDisconnect:
            logger.debug(f"WebSocket {connection_id} disconnected.")
        except Exception as exc:
            logger.exception(f"Unexpected error on connection {connection_id}: {exc}")
        finally:
            await self.disconnect(connection_id)

    async def close_all_connections(self):
        """
        Close all active client and server WebSocket connections.
        """
        connection_ids = await self._client_connections.keys()
        for connection_id in connection_ids:
            await self.disconnect(connection_id)

        connection_ids = await self._server_connections.keys()
        for connection_id in connection_ids:
            await self.disconnect(connection_id)

    async def connection_cleanup(self):
        """
        Clean up all connection maps.

        Invokes cleanup methods for client connections, server connections, and task mappings.
        """
        tasks = [
            self._client_connections.cleanup(),
            self._server_connections.cleanup(),
            self._sid_task_map.cleanup()
        ]
        return await asyncio.gather(*tasks)

    async def run_connection_cleanup(self):
        """
        Periodically run cleanup routines for all connection maps.

        Runs the cleanup routines for client connections, server connections, and task mappings concurrently.
        """
        tasks = [
            self._client_connections.run_cleanup(),
            self._server_connections.run_cleanup(),
            self._sid_task_map.run_cleanup()
        ]
        await asyncio.gather(*tasks)

    async def _update_activity(self, connection_id: str):
        """
        Refresh the activity timestamp for a given client connection.

        :param connection_id: The client connection ID.
        """
        await self._client_connections.refresh(connection_id)


# Global singleton instance for ConnectionManager
INSTANCE: ConnectionManager | None = None


def initialize_connection_manager(comfyui_manager: ComfyUIManager) -> ConnectionManager:
    """
    Initialize the global ConnectionManager singleton with the given ComfyUIManager.

    :param comfyui_manager: Instance of ComfyUIManager.
    :return: The initialized ConnectionManager instance.
    """
    global INSTANCE
    INSTANCE = ConnectionManager(comfyui_manager)
    return INSTANCE


def get_connection_manager() -> ConnectionManager:
    """
    Retrieve the global ConnectionManager instance.

    :return: The ConnectionManager instance.
    :raises ValueError: If the ConnectionManager has not been initialized.
    """
    if not INSTANCE:
        raise ValueError("ConnectionManager not initialized.")
    return INSTANCE
