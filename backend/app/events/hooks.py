"""Real-time event broadcasting hooks for agents, sandboxes, and lifecycle events."""

from typing import Any, Dict, Optional
from backend.app.events.bus import event_bus
from backend.app.schemas.events import TraceHealEvent


async def emit_agent_thought(
    incident_id: str,
    agent_name: str,
    thought: str,
    step: str = "REASONING",
    payload: Optional[Dict[str, Any]] = None,
) -> TraceHealEvent:
    """Broadcasts a live cognitive reasoning step from an autonomous agent."""
    ev = TraceHealEvent(
        topic="agent:thought",
        incident_id=incident_id,
        event_type="AGENT_THINKING",
        actor=agent_name,
        message=thought,
        payload={"step": step, **(payload or {})},
    )
    await event_bus.publish(ev)
    return ev


async def emit_agent_action(
    incident_id: str,
    agent_name: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
) -> TraceHealEvent:
    """Broadcasts an agent tool invocation or operational action."""
    ev = TraceHealEvent(
        topic="agent:action",
        incident_id=incident_id,
        event_type="AGENT_ACTION",
        actor=agent_name,
        message=action,
        payload=details or {},
    )
    await event_bus.publish(ev)
    return ev


async def emit_incident_state_change(
    incident_id: str,
    from_status: str,
    to_status: str,
    reason: str,
    actor: str = "SYSTEM",
) -> TraceHealEvent:
    """Broadcasts an incident lifecycle status transition."""
    ev = TraceHealEvent(
        topic="incident:state",
        incident_id=incident_id,
        event_type="STATUS_CHANGED",
        actor=actor,
        message=f"Incident status changed: {from_status} -> {to_status}",
        payload={"from_status": from_status, "to_status": to_status, "reason": reason},
    )
    await event_bus.publish(ev)
    return ev


async def emit_sandbox_log(
    incident_id: str,
    sandbox_id: str,
    stream: str,
    line: str,
) -> TraceHealEvent:
    """Streams a single line of sandbox process stdout/stderr output."""
    topic = f"sandbox:{stream}"
    ev = TraceHealEvent(
        topic=topic,
        incident_id=incident_id,
        event_type="SANDBOX_OUTPUT",
        actor=f"SANDBOX_{sandbox_id}",
        message=line,
        payload={"sandbox_id": sandbox_id, "stream": stream},
    )
    await event_bus.publish(ev)
    return ev


async def emit_telemetry_spike(
    service_name: str,
    error_rate: float,
    duration_ms: float,
    error_message: str,
    incident_id: Optional[str] = None,
) -> TraceHealEvent:
    """Broadcasts an anomalous error rate or latency spike."""
    ev = TraceHealEvent(
        topic="telemetry:spike",
        incident_id=incident_id,
        event_type="TELEMETRY_SPIKE",
        actor="TELEMETRY_INGESTION",
        message=f"Telemetry anomaly detected in {service_name}: {error_message}",
        payload={
            "service_name": service_name,
            "error_rate": error_rate,
            "duration_ms": duration_ms,
            "error_message": error_message,
        },
    )
    await event_bus.publish(ev)
    return ev


async def emit_system_vital(
    metric_name: str,
    value: float,
    unit: str = "",
    service: str = "cluster",
) -> TraceHealEvent:
    """Broadcasts a live health or performance vital metric."""
    ev = TraceHealEvent(
        topic="system:metric",
        event_type="SYSTEM_VITAL",
        actor="VITAL_MONITOR",
        message=f"{metric_name}: {value}{unit}",
        payload={"metric_name": metric_name, "value": value, "unit": unit, "service": service},
    )
    await event_bus.publish(ev)
    return ev
