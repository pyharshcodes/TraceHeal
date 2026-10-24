"""Incidents REST API endpoints for detection, lifecycle management, and RCA analysis."""

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.rca_agent import RCAAgent
from backend.app.core.utils import safe_json_loads
from backend.app.db.models import Incident
from backend.app.db.session import get_db_session
from backend.app.incidents.detector import IncidentDetector
from backend.app.incidents.service import (
    get_incident,
    list_incidents,
    transition_incident_status,
)
from backend.app.schemas.incident import IncidentRead
from backend.app.telemetry.ingestion import get_all_spans

router = APIRouter(prefix="/incidents", tags=["Incidents"])


class StatusTransitionRequest(BaseModel):
    status: str
    actor: Optional[str] = "OPERATOR"
    reason: Optional[str] = None


@router.post("/detect", status_code=status.HTTP_200_OK)
async def trigger_detection(
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Scans recently ingested spans and correlates failures into active incidents."""
    recent_spans = await get_all_spans(db, limit=200)
    detector = IncidentDetector()
    incidents = await detector.scan_and_correlate(db, recent_spans)

    return {
        "detected_count": len(incidents),
        "incidents": [
            {
                "id": inc.id,
                "title": inc.title,
                "status": inc.status,
                "severity": inc.severity,
                "suspect_service": inc.suspect_service,
            }
            for inc in incidents
        ],
    }


@router.get("", response_model=List[IncidentRead])
@router.get("/", response_model=List[IncidentRead], include_in_schema=False)
async def get_all_incidents(
    status_filter: Optional[str] = Query(None, alias="status"),
    severity_filter: Optional[str] = Query(None, alias="severity"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
):
    """Lists incidents with optional filtering."""
    return await list_incidents(db, status_filter=status_filter, severity_filter=severity_filter, limit=limit)


@router.get("/{incident_id}")
async def get_incident_details(
    incident_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retrieves full incident details including hypotheses, sandbox runs, and audit history."""
    incident = await get_incident(db, incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found.",
        )

    return {
        "id": incident.id,
        "title": incident.title,
        "description": incident.description,
        "status": incident.status,
        "severity": incident.severity,
        "suspect_service": incident.suspect_service,
        "root_cause_summary": incident.root_cause_summary,
        "blast_radius": safe_json_loads(incident.blast_radius_json, {}),
        "created_at": incident.created_at.isoformat(),
        "updated_at": incident.updated_at.isoformat(),
        "hypotheses": [
            {
                "id": h.id,
                "rank": h.rank,
                "title": h.title,
                "description": h.description,
                "suspect_service": h.suspect_service,
                "suspect_component": h.suspect_component,
                "proposed_cause": h.proposed_cause,
                "evidence_summary": h.evidence_summary,
                "status": h.status,
            }
            for h in incident.hypotheses
        ],
        "sandbox_runs": [
            {
                "id": s.id,
                "service_name": s.service_name,
                "status": s.status,
                "exit_code": s.exit_code,
                "reproduction_verified": s.reproduction_verified,
            }
            for s in incident.sandbox_runs
        ],
        "remediations": [
            {
                "id": r.id,
                "patch_type": r.patch_type,
                "policy_check_status": r.policy_check_status,
                "approval_status": r.approval_status,
            }
            for r in incident.remediations
        ],
        "audit_events": [
            {
                "id": a.id,
                "event_type": a.event_type,
                "actor": a.actor,
                "details": safe_json_loads(a.details_json, {}),
                "created_at": a.created_at.isoformat(),
            }
            for a in incident.audit_events
        ],
    }


@router.post("/{incident_id}/analyze")
async def analyze_incident_rca(
    incident_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Invokes the RCA Agent to form causal hypotheses for the incident."""
    agent = RCAAgent()
    try:
        hypotheses = await agent.analyze_incident(db, incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return {
        "incident_id": incident_id,
        "hypotheses_generated": len(hypotheses),
        "hypotheses": [
            {
                "id": h.id,
                "rank": h.rank,
                "title": h.title,
                "description": h.description,
                "proposed_cause": h.proposed_cause,
                "evidence_summary": h.evidence_summary,
            }
            for h in hypotheses
        ],
    }


@router.patch("/{incident_id}/status")
async def update_incident_status(
    incident_id: str,
    req: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Transitions incident status with strict state machine verification."""
    try:
        updated = await transition_incident_status(
            db,
            incident_id=incident_id,
            new_status=req.status,
            actor=req.actor or "OPERATOR",
            reason=req.reason,
        )
        return {
            "incident_id": updated.id,
            "status": updated.status,
            "message": f"Status successfully transitioned to '{updated.status}'",
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
