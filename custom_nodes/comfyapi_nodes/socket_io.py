import asyncio
import struct
import uuid
import aiohttp
import server
from PIL import Image, ImageOps
from io import BytesIO
import logging
from aiohttp import web
from typing import Dict, Tuple, Optional, Union, Any, List

# Fix the ANTIALIAS issue by updating the resampling code
if hasattr(Image, 'Resampling'):
    resampling = Image.Resampling.LANCZOS  # LANCZOS is the replacement for ANTIALIAS
else:
    resampling = Image.BICUBIC  # Better fallback than ANTIALIAS which is deprecated


class BinaryEventTypes:
    """Constants for binary event message types used in WebSocket communication."""
    PREVIEW_IMAGE = 1
    UNENCODED_PREVIEW_IMAGE = 2


MAX_REQUEST_ID_LEN = 32


async def send_socket_catch_exception(function, message):
    """
    Safely execute a WebSocket send operation, catching and logging common connection exceptions.

    Args:
        function: The WebSocket send function to call
        message: The message to send
    """
    try:
        await function(message)
    except (
            aiohttp.ClientError, aiohttp.ClientPayloadError, ConnectionResetError, BrokenPipeError,
            ConnectionError) as err:
        logging.warning(f"WebSocket send error: {err}")


class ComfyApiServer:
    """
    WebSocket server for ComfyUI API handling communication with clients.
    Provides methods for sending JSON data, images, and binary content.
    """

    def __init__(self):
        """Initialize the ComfyAPI WebSocket server with empty socket storage and lock."""
        self.sockets = {}
        self.lock = asyncio.Lock()

    async def send_json(self, event: str, data: Dict[str, Any], sid: str) -> None:
        """
        Send JSON data to specified client(s).

        Args:
            event: Event name to identify the message type
            data: Dictionary containing the payload to send
            sid: Session ID of the client to send to, or None to broadcast
        """
        try:
            if sid:
                async with self.lock:
                    ws = self.sockets.get(sid)
                if ws is not None and not ws.closed:
                    await ws.send_json({"event": event, "data": data})
                    logging.debug(f"JSON message sent to client {sid}: event={event}")
                else:
                    logging.warning(f"Client {sid} not found or connection closed")
        except Exception as e:
            logging.warning(f"Failed to send JSON message: {e}")

    async def send_image(self,
                         image_data: Tuple[str, Image.Image, Optional[int], int],
                         sid: str,
                         req_id: str) -> None:
        """
        Encode and send an image to a client.

        Args:
            image_data: Tuple containing (image_type, image_object, max_size, quality)
            sid: Session ID of the client to send the image to
            req_id: Request ID associated with this image
        """
        try:
            max_length = MAX_REQUEST_ID_LEN
            req_id = req_id[:max_length]

            padded_req_id = req_id.ljust(max_length, "\x00")
            encoded_req_id = padded_req_id.encode("ascii", "replace")

            image_type = image_data[0]
            image = image_data[1]
            max_size = image_data[2]
            quality = image_data[3]

            if max_size is not None:
                image = ImageOps.contain(image, (max_size, max_size), resampling)

            type_num = 1
            if image_type == "JPEG":
                type_num = 1
            elif image_type == "PNG":
                type_num = 2
            elif image_type == "WEBP":
                type_num = 3

            bytes_io = BytesIO()
            try:
                header = struct.pack(">I", type_num)
                # 4 bytes for the type
                bytes_io.write(header)
                # MAX_REQUEST_ID_LEN bytes for the output_id
                bytes_io.write(encoded_req_id)

                image.save(bytes_io, format=image_type, quality=quality, compress_level=1)
                preview_bytes = bytes_io.getvalue()
                await self.send_bytes(BinaryEventTypes.PREVIEW_IMAGE, preview_bytes, sid=sid)
                logging.debug(f"Image sent to client {sid}: type={image_type}, size={len(preview_bytes)} bytes")
            finally:
                bytes_io.close()
        except Exception as e:
            logging.error(f"Failed to send image: {e}")

    async def send_bytes(self, event: int, data: Union[bytes, bytearray], sid: str) -> None:
        """
        Send binary data to specified client(s).

        Args:
            event: Integer event type from BinaryEventTypes
            data: Binary data to send
            sid: Session ID of the client, or None to broadcast
        """
        message = self.encode_bytes(event, data)
        async with self.lock:
            if sid in self.sockets:
                logging.debug(f"Sending binary data to client {sid}: event={event}")
                await send_socket_catch_exception(self.sockets[sid].send_bytes, message)
            else:
                logging.warning(f" ** Client {sid} not found or connection closed")

    @staticmethod
    def encode_bytes(event: int, data: Union[bytes, bytearray]) -> bytearray:
        """
        Encode binary event data for WebSocket transmission.

        Args:
            event: Integer event type from BinaryEventTypes
            data: Binary payload to encode

        Returns:
            Encoded binary message ready for transmission

        Raises:
            RuntimeError: If event type is not an integer
        """
        if not isinstance(event, int):
            raise RuntimeError(f"Binary event types must be integers, got {event}")

        packed = struct.pack(">I", event)
        message = bytearray(packed)
        message.extend(data)
        return message


    async def websocket_handler(self, request):
        """
        Handle WebSocket connections from clients.

        Args:
            request: The HTTP request for the WebSocket connection

        Returns:
            WebSocketResponse object
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        sid = request.rel_url.query.get('clientId', '')

        try:
            await ws.prepare(request)

            async with self.lock:
                if sid:
                    # Reusing existing session, remove old connection
                    if sid in self.sockets:
                        old_ws = self.sockets.pop(sid)
                        if not old_ws.closed:
                            logging.info(f"Closing previous connection for client {sid}")
                            await old_ws.close(code=1001, message=b"New connection established")
                else:
                    sid = uuid.uuid4().hex
                    logging.info(f"Generated new client ID: {sid}")

                # Store new connection
                self.sockets[sid] = ws
                logging.info(f"Client {sid} connected. Total active connections: {len(self.sockets)}")

            # Send initial state to the new client
            await self.send_json("status", {"sid": sid}, sid)

            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        logging.debug(f"Received text message from {sid}: {msg.data[:10]}...")
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        logging.debug(f"Received binary message from {sid}: {len(msg.data)} bytes")
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logging.warning(f"WebSocket connection error from client {sid}: {ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        logging.info(f"WebSocket connection closed by client {sid}")
                        break
            except Exception as e:
                logging.error(f"Error handling WebSocket messages from client {sid}: {e}")
        except Exception as e:
            logging.error(f"Exception during WebSocket handling: {e}")
        finally:
            async with self.lock:
                self.sockets.pop(sid, None)
                logging.info(f"Client {sid} disconnected. Remaining connections: {len(self.sockets)}")

        return ws

comfy_api_server = ComfyApiServer()

# Register the WebSocket handler with the server
@server.PromptServer.instance.routes.get("/comfy-api/ws")
async def websocket_handler(request):
    return await comfy_api_server.websocket_handler(request)

