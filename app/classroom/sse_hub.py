import asyncio
import json
from typing import Dict, Set, Any, Optional

class SSEHub:
    def __init__(self):
        self._class_subscribers: Dict[int, Set[asyncio.Queue]] = {}
        self._board_subscribers: Dict[int, Set[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def _ensure_loop(self):
        if not self._loop:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def subscribe_class(self, class_id: int) -> asyncio.Queue:
        self._ensure_loop()
        q: asyncio.Queue = asyncio.Queue()
        if class_id not in self._class_subscribers:
            self._class_subscribers[class_id] = set()
        self._class_subscribers[class_id].add(q)
        return q

    def unsubscribe_class(self, class_id: int, q: asyncio.Queue):
        if class_id in self._class_subscribers:
            self._class_subscribers[class_id].discard(q)
            if not self._class_subscribers[class_id]:
                del self._class_subscribers[class_id]

    def subscribe_board(self, class_id: int) -> asyncio.Queue:
        self._ensure_loop()
        q: asyncio.Queue = asyncio.Queue()
        if class_id not in self._board_subscribers:
            self._board_subscribers[class_id] = set()
        self._board_subscribers[class_id].add(q)
        return q

    def unsubscribe_board(self, class_id: int, q: asyncio.Queue):
        if class_id in self._board_subscribers:
            self._board_subscribers[class_id].discard(q)
            if not self._board_subscribers[class_id]:
                del self._board_subscribers[class_id]

    def notify_class(self, class_id: int, event_type: str, data: Any):
        self._ensure_loop()
        message = {"event": event_type, "data": data}
        queues = list(self._class_subscribers.get(class_id, []))
        if not queues:
            return

        def _dispatch():
            for q in queues:
                try:
                    q.put_nowait(message)
                except Exception:
                    pass

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(_dispatch)

    def notify_board(self, class_id: int, event_type: str, data: Any):
        self._ensure_loop()
        message = {"event": event_type, "data": data}
        queues = list(self._board_subscribers.get(class_id, []))
        if not queues:
            return

        def _dispatch():
            for q in queues:
                try:
                    q.put_nowait(message)
                except Exception:
                    pass

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(_dispatch)

sse_hub = SSEHub()
