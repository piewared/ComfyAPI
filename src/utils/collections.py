import time
import heapq
import asyncio
from typing import Dict, List, Tuple, Optional, Callable, TypeVar, Generic, Awaitable

T = TypeVar("T")


class TimeoutMap(Generic[T]):
    """
    A mapping of key to object that tracks the last update time for each key and uses a heap
    for efficient cleanup of idle keys.
    """

    def __init__(self, idle_timeout: float, time_function: Optional[Callable[[], float]] = None,
                 evict_callback: Optional[Callable[[str, T], Awaitable[None]]] = None):
        """

        :param idle_timeout:
        :param time_function:
        :param evict_callback:
        """

        self.data: Dict[str, T] = {}
        self.timestamps: Dict[str, float] = {}
        self.idle_timeout = idle_timeout
        self._time = time_function if time_function is not None else time.time
        # Heap elements are tuples: (expiration_time, key)
        self._heap: List[Tuple[float, str]] = []
        self._lock = asyncio.Lock()
        self._evict_callback = evict_callback

    async def keys(self) -> List[str]:
        async with self._lock:
            return list(self.data.keys())

    async def set(self, key: str, value: T) -> None:
        """Add or update an item with the current timestamp."""
        now = self._time()
        async with self._lock:
            self.data[key] = value
            self.timestamps[key] = now
            heapq.heappush(self._heap, (now + self.idle_timeout, key))

    async def get(self, key: str) -> Optional[T]:
        async with self._lock:
            return self.data.get(key, None)

    async def refresh(self, key: str) -> None:
        """Refresh the timestamp for an existing key."""
        now = self._time()
        async with self._lock:
            if key in self.data:
                self.timestamps[key] = now
                heapq.heappush(self._heap, (now + self.idle_timeout, key))

    async def pop(self, key: str) -> Optional[T]:
        """Remove the key and return its value, if it exists."""
        async with self._lock:
            self.timestamps.pop(key, None)
            item = self.data.pop(key, None)

        if self._evict_callback and item:
            await self._evict_callback(key, item)

        return item

    async def cleanup(self) -> None:
        """
        Remove expired keys based on idle_timeout and call the expiration callback for each.

        This method should be called periodically.
        """

        now = self._time()
        expired_keys: List[str] = []
        async with self._lock:
            # Process the heap until the soonest expiration is in the future.
            while self._heap and self._heap[0][0] <= now:
                exp_time, key = heapq.heappop(self._heap)
                last = self.timestamps.get(key)
                if last is None:
                    continue  # Key already removed.
                expected_exp = last + self.idle_timeout
                if expected_exp <= now:
                    expired_keys.append(key)
                else:
                    # The key was updated since it was added to the heap;
                    # push the updated expiration back and break.
                    heapq.heappush(self._heap, (expected_exp, key))
                    break

        for key in expired_keys:
            await self.pop(key)

    async def run_cleanup(self):
        """Periodically run the cleanup method."""
        while True:
            await self.cleanup()
            await asyncio.sleep(1)
