import asyncio
import typing
import time
import uuid

import pytest
from starlette.websockets import WebSocket

from src.comfyui.connection_manager import ConnectionManager


class DummyComfyUIManager:
    async def connect_to_backend(self):
        # Return a dummy backend connection.
        return uuid.uuid4().hex, DummyBackendWebSocket()

class DummyBackendWebSocket:
    async def recv(self):
        await asyncio.sleep(0.01)
        return "backend message"
    async def close(self):
        pass

class DummyWebSocket(WebSocket):
    def __init__(self):
        # Minimal required scope to satisfy Starlette's WebSocket interface.
        self.scope = {"type": "websocket"}
        self.closed = False
        self.messages = []
        self._accepted = False

    async def accept(self, subprotocol: str | None = None,
                     headers: typing.Iterable[tuple[bytes, bytes]] | None = None):
        self._accepted = True

    async def send_json(self, data: typing.Any, mode: str = "text"):
        self.messages.append(("json", data))

    async def send_text(self, message: str):
        self.messages.append(("text", message))

    async def receive_text(self):
        # Simulate a blocking receive.
        await asyncio.sleep(0.1)
        return "dummy message"

    async def close(self, code: int = 1000, reason: str | None = None):
        self.closed = True


class FakeTime:
    """A fake time class that lets us control the time for testing."""
    def __init__(self, start: float = 0.0):
        self.current = start

    def time(self) -> float:
        return self.current

    def advance(self, seconds: float):
        self.current += seconds


@pytest.fixture
def fake_time():
    return FakeTime(start=1000.0)

@pytest.fixture
def manager(fake_time):
    return ConnectionManager(
        idle_timeout=3600,  # 1 hour
        time_function=fake_time.time,
        comfyui_manager=DummyComfyUIManager(),
    )

@pytest.mark.asyncio
async def test_connection_cleanup(manager, fake_time):
    ws = DummyWebSocket()
    conn_id = await manager.accept_client_connection(ws)
    # Verify the connection is active.
    assert conn_id in manager._client_connections
    assert not ws.closed
    # Advance time by 2 hours.
    fake_time.advance(7200)
    # Run one cleanup cycle.
    await manager.connection_cleanup()
    # The connection should now be cleaned up.
    assert conn_id not in manager._client_connections
    assert ws.closed

@pytest.mark.asyncio
async def test_activity_updates_prevent_cleanup(manager, fake_time):
    ws = DummyWebSocket()
    conn_id = await manager.accept_client_connection(ws)
    # Advance fake time by half the idle timeout.
    fake_time.advance(1800)
    # Update the activity.
    await manager._update_activity(conn_id)
    # Advance fake time by another 1800 seconds.
    fake_time.advance(1800)
    await manager.connection_cleanup()
    # The connection should still be active.
    assert conn_id in manager._client_connections
    assert not ws.closed

@pytest.mark.asyncio
async def test_stress_connections_cleanup(manager, fake_time):
    num_connections = 10000
    websockets_list = [DummyWebSocket() for _ in range(num_connections)]
    conn_ids = []
    # Connect all dummy websockets.
    for ws in websockets_list:
        conn_id = await manager.connect(ws)
        conn_ids.append(conn_id)

        await manager.proxy_comfyui_connection(DummyComfyUIManager(), conn_id)


    assert len(manager._client_connections) == num_connections
    assert len(manager.active_backend_connections) == num_connections
    assert len(manager.last_active) == num_connections * 2
    assert len(manager.cid_sid_map) == num_connections
    assert len(manager.sid_cid_map) == num_connections
    assert len(manager.sid_task_map) == num_connections


    # Advance time by 2 hours.
    fake_time.advance(7200)

    # Simulate recent activity for half of the connections.
    for conn_id in conn_ids[: num_connections // 200]:
        await manager._update_activity(conn_id)

    # Get current time so we can profile the cleanup operation.
    start_time = time.perf_counter()
    await manager.cleanup_idle()
    elapsed = time.perf_counter() - start_time
    print(f"cleanup_idle_once executed in {elapsed:.6f} seconds")

    assert len(manager._client_connections) == num_connections // 200
    assert len(manager.active_backend_connections) == num_connections // 200
    assert len(manager.last_active) == (num_connections // 200) * 2
    assert len(manager.cid_sid_map) == num_connections // 200
    assert len(manager.sid_cid_map) == num_connections // 200
    assert len(manager.sid_task_map) == num_connections // 200

    # Check that connections without recent activity are closed.
    for conn_id, ws in zip(conn_ids, websockets_list):
        if conn_id in manager.last_active:
            # These connections should remain active.
            assert not ws.closed
        else:
            # Idle connections should have been cleaned up.
            assert ws.closed

    await manager.close_all_connections()