"""Incident service managing lifecycle transitions, validation, and audit tracking."""

import json
from typing import List, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AuditEvent, Incident
from backend.app.schemas.incident import IncidentCreate, IncidentUpdate

VALID_TRANSITIONS = {
    "DETECTED": ["INVESTIGATING", "CLOSED"],
    "INVESTIGATING": ["REPRODUCING", "CLOSED"],
    "REPRODUCING": ["VERIFIED", "INVESTIGATING", "CLOSED"],
    "VERIFIED": ["REMEDIATED", "CLOSED"],
    "REMEDIATED": ["RESOLVED", "VERIFIED", "CLOSED"],
    "RESOLVED": ["CLOSED"],
    "CLOSED": [],
}


async def get_incident(db: AsyncSession, incident_id: str) -> Optional[Incident]:
    """Fetches an incident by ID with relationships eagerly loaded."""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    inc = result.scalar_one_or_none()
    if inc:
        await db.refresh(inc, ["audit_events", "hypotheses", "sandbox_runs", "remediations"])
    return inc


async def list_incidents(
    db: AsyncSession,
    status_filter: Optional[str] = None,
    severity_filter: Optional[str] = None,
    limit: int = 50,
) -> List[Incident]:
    stmt = select(Incident)
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter)
    if severity_filter:
        stmt = stmt.where(Incident.severity == severity_filter)
    stmt = stmt.order_by(desc(Incident.created_at)).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def transition_incident_status(
    db: AsyncSession,
    incident_id: str,
    new_status: str,
    actor: str = "SYSTEM",
    reason: Optional[str] = None,
) -> Incident:
    """Safely transitions an incident's lifecycle status with strict state machine validation."""
    incident = await get_incident(db, incident_id)
    if not incident:
        raise ValueError(f"Incident '{incident_id}' not found.")

    curr_status = incident.status
    if new_status == curr_status:
        return incident

    allowed = VALID_TRANSITIONS.get(curr_status, [])

    if new_status not in allowed:
        raise ValueError(
            f"Illegal incident transition from '{curr_status}' to '{new_status}'. "
            f"Allowed next states: {allowed}"
        )

    old_status = incident.status
    incident.status = new_status

    # Record Audit Event
    audit = AuditEvent(
        incident_id=incident.id,
        event_type="STATUS_TRANSITION",
        actor=actor,
        details_json=json.dumps({
            "from_status": old_status,
            "to_status": new_status,
            "reason": reason or "Normal lifecycle progression",
        }),
    )
    db.add(audit)
    await db.commit()
    await db.refresh(incident)

    # Emit real-time event notification
    try:
        from backend.app.events.hooks import emit_incident_state_change
        await emit_incident_state_change(
            incident_id=incident.id,
            from_status=old_status,
            to_status=new_status,
            reason=reason or "Normal lifecycle progression",
            actor=actor,
        )
    except Exception:
        pass

    return incident


class IncidentService:
    """Class wrapper providing incident lifecycle operations."""

    @staticmethod
    async def get_incident(db: AsyncSession, incident_id: str) -> Optional[Incident]:
        return await get_incident(db, incident_id)

    @staticmethod
    async def list_incidents(
        db: AsyncSession,
        status_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Incident]:
        return await list_incidents(db, status_filter, severity_filter, limit)

    @staticmethod
    async def update_incident_status(
        db: AsyncSession,
        incident_id: str,
        new_status: str,
        actor: str = "SYSTEM",
        details: Optional[dict] = None,
        reason: Optional[str] = None,
    ) -> Incident:
        r = reason or (json.dumps(details) if details else None)
        return await transition_incident_status(db, incident_id, new_status, actor, r)

    @staticmethod
    async def transition_incident_status(
        db: AsyncSession,
        incident_id: str,
        new_status: str,
        actor: str = "SYSTEM",
        reason: Optional[str] = None,
    ) -> Incident:
        return await transition_incident_status(db, incident_id, new_status, actor, reason)

