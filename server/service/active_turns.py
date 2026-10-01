"""
In-flight active turn manager for independent background agent runs.

Decouples agent execution from individual HTTP SSE request connections.
Allows tasks to keep running in the background when the user navigates
away or switches sessions, and enables stream reconnection with historical
event replay.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

from server.service.events import sse_frame

logger = logging.getLogger(__name__)


@dataclass
class ActiveTurn:
    task_id: str
    lock: asyncio.Lock
    worker_task: asyncio.Task | None = None
    title_worker_task: asyncio.Task | None = None
    frames_history: list[str] = field(default_factory=list)
    subscribers: set[asyncio.Queue[str | object]] = field(default_factory=set)
    sentinel: object = field(default_factory=object)
    status: str = "running"
    created_at: float = field(default_factory=time.time)
    _finished: bool = False

    async def broadcast(self, frame: str) -> None:
        """Record an SSE frame and push it to all active subscriber queues."""
        self.frames_history.append(frame)
        for queue in list(self.subscribers):
            try:
                await queue.put(frame)
            except Exception:  # noqa: BLE001
                pass

    async def finish(self, status: str = "completed") -> None:
        """Mark turn as finished and signal all current subscribers to exit."""
        if self._finished:
            return
        self._finished = True
        self.status = status
        for queue in list(self.subscribers):
            try:
                await queue.put(self.sentinel)
            except Exception:  # noqa: BLE001
                pass

    async def abort(self) -> None:
        """Cancel running worker tasks and broadcast aborted done frame."""
        self.status = "aborted"
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
        if self.title_worker_task and not self.title_worker_task.done():
            self.title_worker_task.cancel()
        if self.lock and self.lock.locked():
            self.lock.release()
        aborted_frame = sse_frame("done", {"task_status": "aborted"})
        await self.broadcast(aborted_frame)
        await self.finish("aborted")

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """Subscribe to this turn's events.

        First yields all previously accumulated frames (replay), then yields
        live frames as they arrive until the turn finishes.
        """
        queue: asyncio.Queue[str | object] = asyncio.Queue()
        self.subscribers.add(queue)

        try:
            # 1. Replay historical frames produced before this subscriber connected
            for frame in list(self.frames_history):
                yield frame

            # If the turn already finished before or during replay, we are done
            if self._finished:
                return

            # 2. Stream live frames
            while True:
                item = await queue.get()
                if item is self.sentinel:
                    break
                yield str(item)
        finally:
            self.subscribers.discard(queue)


class ActiveTurnManager:
    """Registry of currently executing turns keyed by task_id."""

    def __init__(self) -> None:
        self._turns: dict[str, ActiveTurn] = {}

    def get(self, task_id: str) -> ActiveTurn | None:
        return self._turns.get(task_id)

    def is_running(self, task_id: str) -> bool:
        turn = self._turns.get(task_id)
        return turn is not None and turn.status == "running"

    def create_turn(self, task_id: str, lock: asyncio.Lock | None = None) -> ActiveTurn:
        turn = ActiveTurn(task_id=task_id, lock=lock)
        self._turns[task_id] = turn
        return turn

    def remove(self, task_id: str) -> ActiveTurn | None:
        return self._turns.pop(task_id, None)

    async def abort(self, task_id: str) -> bool:
        turn = self._turns.get(task_id)
        if turn is None:
            return False
        await turn.abort()
        self._turns.pop(task_id, None)
        return True


active_turn_manager = ActiveTurnManager()
