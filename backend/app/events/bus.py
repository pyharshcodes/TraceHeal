"""Asynchronous Event Bus & Pub/Sub Hub.

Provides wildcard topic subscriptions, backpressure-managed client queues,
and an in-memory replay ring buffer for live SSE event streaming.
"""

import asyncio
from collections import deque
import fnmatch
from typing import Deque, Dict, List, Optional, Set, Tuple

from backend.app.schemas.events import TraceHealEvent


class EventBus:
    """Central asynchronous Pub/Sub event hub with wildcard routing and replay buffer."""

    def __init__(self, buffer_size: int = 300, queue_maxsize: int = 100):
        self._buffer: Deque[TraceHealEvent] = deque(maxlen=buffer_size)
        self._queue_maxsize = queue_maxsize
        # Map: asyncio.Queue -> (topic_pattern, filter_incident_id)
        self._subscribers: Dict[asyncio.Queue, Tuple[str, Optional[str]]] = {}
        self._lock = asyncio.Lock()

    def _matches_topic(self, pattern: str, topic: str) -> bool:
        """Evaluates whether topic matches subscription pattern (supports * wildcards)."""
        if pattern == "*" or pattern == topic:
            return True
        return fnmatch.fnmatch(topic, pattern)

    def _matches_incident(self, filter_id: Optional[str], event_incident_id: Optional[str]) -> bool:
        """Evaluates incident filtering criteria."""
        if not filter_id:
            return True
        return event_incident_id == filter_id or event_incident_id is None

    async def publish(self, event: TraceHealEvent) -> int:
        """Publishes an event to matching subscribers and appends to replay buffer."""
        async with self._lock:
            # 1. Append to ring buffer for historical replaying
            self._buffer.append(event)

            # 2. Broadcast to all matching subscriber queues
            delivery_count = 0
            for queue, (pattern, filter_inc_id) in list(self._subscribers.items()):
                if self._matches_topic(pattern, event.topic) and self._matches_incident(filter_inc_id, event.incident_id):
                    # Handle backpressure: if subscriber queue is full, discard oldest item
                    if queue.full():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        queue.put_nowait(event)
                        delivery_count += 1
                    except asyncio.QueueFull:
                        pass

            return delivery_count

    async def subscribe(
        self,
        topic_pattern: str = "*",
        incident_id: Optional[str] = None,
        replay_last: int = 0,
    ) -> asyncio.Queue:
        """Subscribes to topics and optionally replays historical events from the buffer."""
        queue: asyncio.Queue[TraceHealEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
        async with self._lock:
            self._subscribers[queue] = (topic_pattern, incident_id)

            # Replay historical events
            if replay_last > 0 and len(self._buffer) > 0:
                matching_history = [
                    ev for ev in self._buffer
                    if self._matches_topic(topic_pattern, ev.topic) and self._matches_incident(incident_id, ev.incident_id)
                ]
                replayed = matching_history[-replay_last:]
                for ev in replayed:
                    try:
                        queue.put_nowait(ev)
                    except asyncio.QueueFull:
                        break

        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Removes a subscriber queue."""
        async with self._lock:
            if queue in self._subscribers:
                del self._subscribers[queue]

    def get_history(
        self,
        topic_pattern: str = "*",
        incident_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[TraceHealEvent]:
        """Retrieves matching historical events from the ring buffer."""
        matching = [
            ev for ev in self._buffer
            if self._matches_topic(topic_pattern, ev.topic) and self._matches_incident(incident_id, ev.incident_id)
        ]
        return matching[-limit:]

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def clear(self) -> None:
        """Clears buffer and active subscriptions (used for clean test resets)."""
        self._buffer.clear()
        self._subscribers.clear()


# Global singleton instance
event_bus = EventBus()
