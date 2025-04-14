import asyncio
import json
import re
import signal
import uuid
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional, Callable, Pattern, Literal, Awaitable
from uuid import uuid4

import aiohttp
import websockets
from loguru import logger
from pydantic import BaseModel

from src.comfyui.comfyui_workspace import set_workspace, ensure_workspace_initialized
from src.utils.collections import TimeoutMap
from src.utils.logger_config import get_comfyui_logger
from src.comfyui.workflow_analysis import WorkflowDescriptor
from src.config import get_comfyui_settings

comfyui_logger = get_comfyui_logger()

comfyui_settings = get_comfyui_settings()

COMFYUI_ADDRESS_REGEX: Pattern = re.compile(r"go to: (http://\d+\.\d+\.\d+\.\d+:\d+)")
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds

class ComfyUIStatus(str, Enum):
    NOT_RUNNING = "not_running"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class WorkflowTask(BaseModel):
    prompt_id: str
    request_id: str
    image_ws_sid: str
    prompt: WorkflowDescriptor
    executing_node_id: Optional[str] = None
    status: Literal["queued", "running", "completed", "failed", "interrupted"]

class ComfyUIManager:
    def __init__(self):
        self.python_path = comfyui_settings.interpreter_path
        self.main_script = comfyui_settings.main_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self.lock = asyncio.Lock()
        self.monitor_status_task: Optional[asyncio.Task] = None
        self.monitor_ws_task: Optional[asyncio.Task] = None
        self.stream_tasks: list[asyncio.Task] = []
        self._start_timeout_s = 20
        self._status_check_interval_s = 10
        self._comfyui_address: Optional[str] = None
        self._prompt_to_job_map: TimeoutMap[WorkflowTask] = TimeoutMap(idle_timeout=60*60*24) # Timeout of 24 hours
        self._prompt_to_callback_map: TimeoutMap[Callable] = TimeoutMap(idle_timeout=60*60*24) # Timeout of 24 hours
        self._request_id_to_prompt: TimeoutMap[str] = TimeoutMap(idle_timeout=60 * 60 * 24)  # Timeout of 24 hours
        self._status_socket_sid = uuid4().hex


    async def start(self) -> ComfyUIStatus:
        """
        Start the ComfyUI process.
        :return:
        """
        logger.info("Ensuring workspace is initialized")
        await ensure_workspace_initialized()

        async with self.lock:
            if await self._check_if_running():
                logger.info("ComfyUI is already running")
                return ComfyUIStatus.RUNNING

            logger.info("Starting ComfyUI")
            try:
                # Create the subprocess asynchronously with decoded output.
                self.process = await asyncio.create_subprocess_exec(
                    self.python_path,
                    self.main_script, '--listen', comfyui_settings.listen_address,
                    '--port', str(comfyui_settings.listen_port),
                    '--base-directory', str(comfyui_settings.workspace_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                # Launch asynchronous stream readers.
                if self.process.stdout:
                    self.stream_tasks.append(asyncio.create_task(
                        self._stream_reader(self.process.stdout, "stdout",
                                              scan_regex=COMFYUI_ADDRESS_REGEX,
                                              scan_callback=self._get_host_port)
                    ))
                if self.process.stderr:
                    self.stream_tasks.append(asyncio.create_task(
                        self._stream_reader(self.process.stderr, "stderr",
                                              scan_regex=COMFYUI_ADDRESS_REGEX,
                                              scan_callback=self._get_host_port)
                    ))

                await asyncio.sleep(1)
                if self.process.returncode is not None:
                    # Process terminated prematurely.
                    stdout, stderr = await self.process.communicate()
                    error_message = stderr.strip() or "Process terminated unexpectedly."
                    logger.error(f"ComfyUI failed to start: {error_message}")
                    return ComfyUIStatus.NOT_RUNNING

                # Monitor the startup process.
                self.stream_tasks.append(asyncio.create_task(self._wait_for_start()))

                return ComfyUIStatus.STARTING
            except Exception:
                logger.exception("Failed to start ComfyUI")
                return ComfyUIStatus.NOT_RUNNING

    async def stop(self) -> ComfyUIStatus:
        """
        Stop the ComfyUI process.
        :return:
        """
        async with self.lock:
            if self.process is None or self.process.returncode is not None:
                return ComfyUIStatus.NOT_RUNNING

            logger.info("Stopping ComfyUI")
            try:
                self.process.send_signal(signal.SIGINT)
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.info("Process did not exit gracefully, terminating")
                    self.process.terminate()
                    await asyncio.wait_for(self.process.wait(), timeout=5)
            except Exception:
                logger.exception("Error stopping ComfyUI")
                return ComfyUIStatus.ERROR
            finally:
                self.process = None
                if self.monitor_status_task:
                    self.monitor_status_task.cancel()
                    self.monitor_status_task = None
                for task in self.stream_tasks:
                    task.cancel()

                # Clear the stream tasks list.
                self.stream_tasks.clear()


            return ComfyUIStatus.NOT_RUNNING

    async def change_workspace(self, workspace_tar: bytes) -> None:
        await self.stop()
        await set_workspace(workspace_tar)
        await self.start()

    async def status(self) -> ComfyUIStatus:
        async with self.lock:
            return ComfyUIStatus.RUNNING if await self._check_if_running() else ComfyUIStatus.NOT_RUNNING

    async def run_workflow(self, sid: str,  request_id: str, descriptor: WorkflowDescriptor,
                           status_callback: Callable[[WorkflowTask], Awaitable[None]]):
        """
        Run the workflow with the given descriptor.
        :param request_id:
        :param status_callback:
        :param sid:
        :param descriptor:
        :return:
        """

        descriptor.outputs[0].connection_id = sid
        descriptor.outputs[0].output_id = request_id

        # Replace the input values with the new values.
        for new_input in descriptor.inputs:
            descriptor.nodes[new_input.node_id]["inputs"]["input_id"] = new_input.value

        for new_output in descriptor.outputs:
            descriptor.nodes[new_output.node_id]["inputs"]["output_id"] = new_output.output_id
            descriptor.nodes[new_output.node_id]["inputs"]["client_id"] = new_output.connection_id

        p = {"prompt": descriptor.workflow_json, "client_id": self._status_socket_sid}
        data = json.dumps(p).encode('utf-8')

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._comfyui_address}/prompt", data=data) as response:
                if response.status != 200:
                    raise Exception(f"Failed to run workflow: {response.status}")
                response_data = await response.json()

                prompt_id = None
                if response_data and (prompt_id := response_data.get('prompt_id')):
                    logger.debug(f"Workflow started with prompt ID: {prompt_id}")

                if not prompt_id:
                    raise Exception("Failed to start workflow")

                new_task = WorkflowTask(prompt_id=prompt_id, request_id=request_id, image_ws_sid=sid, prompt=descriptor, status="queued")
                await self._prompt_to_job_map.set(prompt_id, new_task)
                await self._prompt_to_callback_map.set(prompt_id, status_callback)
                await self._request_id_to_prompt.set(request_id, prompt_id)
                await status_callback(new_task)


    async def connect_to_backend(self, sid: str = None) -> tuple[str, websockets.ClientConnection]:
        """
        Connect to the ComfyUI deploy websocket for receiving image outputs.
        This method will retry multiple times before giving up.
        :return:
        """
        for attempt in range(1, MAX_RETRIES + 1):
            backend_ws = None
            try:
                if sid:
                    url = f"{self._comfyui_address}/comfy-api/ws?clientId={sid}".replace('http', 'ws')
                else:
                    url = f"{self._comfyui_address}/comfy-api/ws".replace('http', 'ws')

                backend_ws = await websockets.connect(url)
                message = await backend_ws.recv()
                sid = json.loads(message).get("data").get("sid")
                if sid:
                    logger.info(f"Connected to backend on attempt {attempt}")
                    return sid, backend_ws
                else:
                    await backend_ws.close()
            except Exception as e:
                logger.warning(f"Attempt {attempt}: Backend connection failed: {e}")
                if backend_ws:
                    await backend_ws.close()
                await asyncio.sleep(RETRY_DELAY * attempt)

        raise ConnectionError("Failed to connect to backend after multiple attempts.")

    async def _check_if_running(self) -> bool:
        """
        Check if the ComfyUI process is running by attempting to connect to its HTTP server.
        Assumes that the lock is held.
        """
        if not self._comfyui_address or self.process is None or self.process.returncode is not None:
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self._comfyui_address) as response:
                    return response.status == 200
        except Exception:
            return False

    async def _stream_reader(self, pipe: asyncio.StreamReader, name: str,
                             scan_regex: Optional[Pattern] = None,
                             scan_callback: Optional[Callable[[str], None]] = None):
        while True:
            line = await pipe.readline()
            if not line:
                break

            # Already a decoded string because of the encoding parameter.
            line_str = line.strip().decode('utf-8')
            if scan_regex and scan_callback and scan_regex.search(line_str):
                scan_callback(line_str)

            comfyui_logger.info(f"[{name}] {line_str}")

    async def _wait_for_start(self):
        for _ in range(self._start_timeout_s):
            if await self._check_if_running():
                self.monitor_status_task = asyncio.create_task(self._monitor_system_stats())
                self.monitor_ws_task = asyncio.create_task(self._monitor_status_socket())
                self.stream_tasks.append(self.monitor_status_task)
                self.stream_tasks.append(self.monitor_ws_task)
                return
            logger.info("Waiting for ComfyUI to start...")
            await asyncio.sleep(1)
        logger.error("ComfyUI failed to start within the timeout period")

    def _get_host_port(self, line: str):
        """Extracts the ComfyUI address from a given line of output."""
        match = COMFYUI_ADDRESS_REGEX.search(line)
        if match:
            self._comfyui_address = match.group(1)
        return None

    async def _monitor_system_stats(self):
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self._comfyui_address}/system_stats") as response:
                        if response.status == 200:
                            stats = await response.json()
                            logger.debug(f"System stats: {stats}")
                        else:
                            logger.warning(f"Failed to fetch system stats: {response.status}")
            except Exception:
                logger.exception("Error fetching system stats")
            await asyncio.sleep(self._status_check_interval_s)

    async def _monitor_status_socket(self) -> None:
        for attempt in range(1, MAX_RETRIES + 1):
            backend_ws = None
            try:
                backend_ws = await websockets.connect(
                    f"{self._comfyui_address}/ws?clientId={self._status_socket_sid}".replace('http', 'ws'))

                message = await backend_ws.recv()
                sid = json.loads(message).get("data").get("sid")
                if sid and sid == self._status_socket_sid:
                    logger.info(f"Connected to backend status socket on attempt {attempt}")
                else:
                    await backend_ws.close()
                    continue
                try:
                    while True:
                        message = await backend_ws.recv()
                        if not isinstance(message, str):
                            raise ValueError("Received non-string message")
                        message_dict = json.loads(message)

                        msg_type = message_dict.get("type")
                        data = message_dict.get("data", {})
                        prompt_id = data.get("prompt_id")
                        if not prompt_id:
                            continue  # or handle missing prompt_id as needed

                        # Common operations: refresh and fetch the current job and callback
                        await self._prompt_to_job_map.refresh(prompt_id)
                        wf_status = await self._prompt_to_job_map.get(prompt_id)
                        callback = await self._prompt_to_callback_map.get(prompt_id)
                        if wf_status is None or callback is None:
                            continue

                        # Consolidate status assignment based on message type
                        if msg_type in ("execution_start", "executing"):
                            wf_status.status = "running"
                        elif msg_type == "execution_success":
                            wf_status.status = "completed"
                        elif msg_type == "execution_error":
                            wf_status.status = "failed"
                        elif msg_type == "execution_interrupted":
                            wf_status.status = "interrupted"
                        elif msg_type == "execution_cached":
                            wf_status.status = "completed"
                        else:
                            logger.error(f"Unknown message type: {msg_type}")
                            continue

                        # Apply additional updates for specific message types
                        if msg_type == "executing":
                            wf_status.executing_node_id = data.get("node")

                        await callback(wf_status)

                        # If the job finished, clear the maps
                        if wf_status.status in ("completed", "failed", "interrupted"):
                            await self._prompt_to_job_map.pop(prompt_id)
                            await self._prompt_to_callback_map.pop(prompt_id)
                            await self._request_id_to_prompt.pop(wf_status.request_id)

                        logger.debug(f"Received message on connection {sid}: {message}")

                except websockets.exceptions.ConnectionClosedError:
                    logger.debug(f"WebSocket {sid} disconnected.")
                except Exception as exc:
                    logger.exception(f"Unexpected error on connection {sid}: {exc}")
                finally:
                    await backend_ws.close()

            except Exception as e:
                logger.warning(f"Attempt {attempt}: Backend connection failed: {e}")
                if backend_ws:
                    await backend_ws.close()
                await asyncio.sleep(RETRY_DELAY * attempt)

        raise ConnectionError("Failed to connect to backend after multiple attempts.")



@lru_cache(maxsize=1)
def get_manager() -> ComfyUIManager:
    manager = ComfyUIManager()
    return manager