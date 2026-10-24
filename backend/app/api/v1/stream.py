"""Real-Time Event Streaming & SSE API Endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.app.events.bus import event_bus
from backend.app.events.streaming import event_stream_generator
from backend.app.schemas.events import EventPublishRequest, TraceHealEvent

router = APIRouter(prefix="/stream", tags=["Real-Time Streaming"])


@router.get("/events")
async def stream_all_events(
    request: Request,
    topic: str = Query("*", description="Topic subscription filter with optional wildcard e.g. agent:*"),
    incident_id: Optional[str] = Query(None, description="Optional incident ID filter"),
    replay: int = Query(20, ge=0, le=200, description="Number of historical events to replay upon connection"),
    max_events: Optional[int] = Query(None, description="Optional maximum events to yield before closing stream"),
):
    """Universal Server-Sent Events (SSE) stream for live agent thoughts, telemetry, and system events."""
    return StreamingResponse(
        event_stream_generator(
            topic=topic,
            incident_id=incident_id,
            replay=replay,
            request=request,
            max_events=max_events,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/incidents/{incident_id}")
async def stream_incident_terminal(
    incident_id: str,
    request: Request,
    replay: int = Query(30, ge=0, le=200, description="Historical events to replay"),
    max_events: Optional[int] = Query(None, description="Optional maximum events to yield before closing stream"),
):
    """Dedicated SSE terminal stream for an active incident investigation."""
    return StreamingResponse(
        event_stream_generator(
            topic="*",
            incident_id=incident_id,
            replay=replay,
            request=request,
            max_events=max_events,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/metrics")
async def stream_metrics(
    request: Request,
    replay: int = Query(10, ge=0, le=100),
    max_events: Optional[int] = Query(None),
):
    """Dedicated SSE stream for live telemetry spikes and system health vitals."""
    return StreamingResponse(
        event_stream_generator(
            topic="system:*",
            replay=replay,
            request=request,
            max_events=max_events,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/publish", status_code=status.HTTP_201_CREATED)
async def publish_event(req: EventPublishRequest):
    """Programmatically publishes a custom event to the Pub/Sub bus and active SSE streams."""
    event = TraceHealEvent(
        topic=req.topic,
        event_type=req.event_type,
        actor=req.actor,
        message=req.message,
        incident_id=req.incident_id,
        payload=req.payload or {},
    )
    delivered = await event_bus.publish(event)
    return {
        "status": "PUBLISHED",
        "event_id": event.id,
        "topic": event.topic,
        "subscribers_delivered": delivered,
        "timestamp": event.timestamp,
    }


@router.get("/history", response_model=List[TraceHealEvent])
async def get_event_history(
    topic: str = Query("*"),
    incident_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieves recent events from the in-memory replay buffer."""
    return event_bus.get_history(topic_pattern=topic, incident_id=incident_id, limit=limit)
