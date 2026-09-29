"""WebSocket event hub (PROMPT §20, §24).

Buffers agent events per task and fans them out to connected sidebars. Events
are produced on the agent worker thread; the hub uses ordinary thread-safe
``queue.Queue`` objects so it does not depend on any particular asyncio loop
(this keeps it correct under uvicorn and under the test client alike). The WS
handler drains its queue with short timeouts inside a thread.
"""

from __future__ import annotations

import queue
import threading
from collections import defaultdict, deque

from agent.core.events import AgentEvent


class EventHub:
    """One hub for the whole service; keyed by task id."""

    def __init__(self, backlog: int = 500) -> None:
        self._subscribers: dict[str, set[queue.Queue]] = defaultdict(set)
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=backlog))
        self._lock = threading.Lock()

    def publish(self, event: AgentEvent) -> None:
        """Called from the agent worker thread; thread-safe."""
        wire = event.to_wire()
        with self._lock:
            self._history[event.task_id].append(wire)
            for q in list(self._subscribers.get(event.task_id, ())):
                q.put_nowait(wire)

    # Back-compat alias used by the server wiring.
    publish_threadsafe = publish

    def subscribe(self, task_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            for wire in self._history.get(task_id, ()):
                q.put_nowait(wire)
            self._subscribers[task_id].add(q)
        return q

    def unsubscribe(self, task_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(task_id)
            if subs and q in subs:
                subs.remove(q)

    # No-op kept so existing startup wiring stays valid.
    def bind_loop(self, loop) -> None:  # noqa: D401
        return None
