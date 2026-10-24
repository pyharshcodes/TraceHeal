"""Pydantic schemas for Real-Time Event Streaming & SSE Protocols."""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


def generate_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:10]}"


def current_iso_time() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceHealEvent(BaseModel):
    """Structured event packet distributed over Pub/Sub bus and SSE stream."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=generate_event_id)
    topic: str = Field(..., description="e.g. agent:thought, incident:state, sandbox:stdout, telemetry:span")
    incident_id: Optional[str] = None
    event_type: str = Field(..., description="Specific event verb e.g. AGENT_THINKING, STATUS_CHANGE")
    actor: str = Field(default="SYSTEM")
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=current_iso_time)


class EventPublishRequest(BaseModel):
    """Request payload to manually publish an event to the bus."""
    topic: str
    event_type: str
    message: str
    incident_id: Optional[str] = None
    actor: str = Field(default="API")
    payload: Optional[Dict[str, Any]] = None
