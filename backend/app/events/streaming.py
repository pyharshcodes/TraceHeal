"""Server-Sent Events (SSE) Stream Formatter and Generator.

Conforms to standard W3C text/event-stream specification with automated
keepalive heartbeats, disconnect detection, and clean connection teardown.
"""

import asyncio
from typing import Any, AsyncGenerator, Optional

from backend.app.events.bus import event_bus
from backend.app.schemas.events import TraceHealEvent


def format_sse(event: TraceHealEvent) -> str:
    """Formats a TraceHealEvent into standard text/event-stream message syntax."""
    return f"id: {event.id}\nevent: {event.topic}\ndata: {event.model_dump_json()}\n\n"


async def event_stream_generator(
    topic: str = "*",
    incident_id: Optional[str] = None,
    replay: int = 20,
    heartbeat_sec: float = 15.0,
    request: Optional[Any] = None,
    max_events: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """Asynchronous generator yielding SSE formatted event strings, pings, and disconnects cleanly."""
    queue = await event_bus.subscribe(topic_pattern=topic, incident_id=incident_id, replay_last=replay)
    sent_count = 0
    try:
        # Initial connection acknowledgment comment
        yield f": connected to TraceHeal event stream (topic={topic})\n\n"

        while True:
            if request is not None and hasattr(request, "is_disconnected"):
                try:
                    if await request.is_disconnected():
                        break
                except Exception:
                    pass

            if max_events is not None and sent_count >= max_events:
                break

            try:
                event: TraceHealEvent = await asyncio.wait_for(queue.get(), timeout=min(heartbeat_sec, 0.5))
                yield format_sse(event)
                sent_count += 1
            except asyncio.TimeoutError:
                if request is not None and hasattr(request, "is_disconnected"):
                    try:
                        if await request.is_disconnected():
                            break
                    except Exception:
                        pass
                yield ": ping\n\n"
                if max_events is not None:
                    sent_count += 1
    finally:
        await event_bus.unsubscribe(queue)
