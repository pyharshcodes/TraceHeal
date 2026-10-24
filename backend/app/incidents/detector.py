"""Autonomous incident detector and alert correlation engine."""

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AuditEvent, Incident, TelemetrySpan
from backend.app.telemetry.critical_path import identify_failure_origin, is_error_span
from backend.app.telemetry.service_graph import build_service_dependency_graph


class IncidentDetector:
    """Evaluates telemetry spans, detects anomaly patterns, and correlates

    multi-service error storms into unified incident records.
    """

    def __init__(self, error_rate_threshold: float = 0.15):
        self.error_rate_threshold = error_rate_threshold

    async def scan_and_correlate(
        self,
        db: AsyncSession,
        spans: List[TelemetrySpan],
    ) -> List[Incident]:
        """Analyzes a collection of spans, detects incidents, and correlates

        cascading errors into consolidated Incident entities.
        """
        if not spans:
            return []

        # 1. Group spans by trace_id
        traces_map = defaultdict(list)
        for s in spans:
            traces_map[s.trace_id].append(s)

        # 2. Identify traces with errors and determine failure origins
        error_traces: List[str] = []
        origin_reports = {}

        for trace_id, trace_spans in traces_map.items():
            has_error = any(is_error_span(s.__dict__) for s in trace_spans)
            if has_error:
                error_traces.append(trace_id)
                origin_report = identify_failure_origin(trace_spans)
                origin_reports[trace_id] = origin_report

        if not error_traces:
            return []

        # 3. Group by suspect service identified by causal origin analysis
        service_incident_groups = defaultdict(list)
        for trace_id in error_traces:
            origin = origin_reports[trace_id]
            suspect_svc = origin.service_name or "unknown-service"
            service_incident_groups[suspect_svc].append(trace_id)

        created_incidents: List[Incident] = []

        # 4. Check for existing active incidents or create new ones
        for suspect_svc, trace_ids in service_incident_groups.items():
            # Check if active incident already exists for this service
            stmt = (
                select(Incident)
                .where(Incident.suspect_service == suspect_svc)
                .where(Incident.status.notin_(["RESOLVED", "CLOSED"]))
            )
            result = await db.execute(stmt)
            existing_incident = result.scalars().first()

            # Gather all affected spans across all traces in this group
            correlated_spans: List[TelemetrySpan] = []
            affected_services = set()
            impacted_endpoints = set()
            sample_errors = []

            for t_id in trace_ids:
                for s in traces_map[t_id]:
                    correlated_spans.append(s)
                    affected_services.add(s.service_name)
                    impacted_endpoints.add(f"{s.operation_name}")
                    if s.error_message and len(sample_errors) < 3:
                        sample_errors.append(s.error_message)

            primary_origin = origin_reports[trace_ids[0]]
            error_sig = primary_origin.error_message or "Unknown failure condition"

            blast_radius = {
                "affected_services": sorted(list(affected_services)),
                "impacted_endpoints": sorted(list(impacted_endpoints)),
                "correlated_traces_count": len(trace_ids),
                "error_spans_count": len([s for s in correlated_spans if is_error_span(s.__dict__)]),
                "primary_error_signature": error_sig,
            }

            if existing_incident:
                # Correlate additional spans to existing incident
                for s in correlated_spans:
                    s.incident_id = existing_incident.id
                existing_incident.blast_radius_json = json.dumps(blast_radius)
                await db.commit()
                await db.refresh(existing_incident)
                created_incidents.append(existing_incident)
            else:
                # Create brand new Incident
                severity = "CRITICAL" if len(affected_services) > 1 or "Pool" in error_sig else "HIGH"
                title = f"[{suspect_svc}] {primary_origin.operation_name or 'Service'} Degradation"
                description = (
                    f"Automated detection identified cascading failure originated in {suspect_svc}. "
                    f"Signature: {error_sig}. Blast radius encompasses {len(affected_services)} services."
                )

                incident = Incident(
                    title=title,
                    description=description,
                    status="DETECTED",
                    severity=severity,
                    suspect_service=suspect_svc,
                    blast_radius_json=json.dumps(blast_radius),
                )
                db.add(incident)
                await db.commit()
                await db.refresh(incident)

                # Link correlated spans
                for s in correlated_spans:
                    s.incident_id = incident.id

                # Append Audit Event
                audit_event = AuditEvent(
                    incident_id=incident.id,
                    event_type="INCIDENT_DETECTED",
                    actor="DETECTOR_ENGINE",
                    details_json=json.dumps({
                        "suspect_service": suspect_svc,
                        "severity": severity,
                        "correlated_traces": len(trace_ids),
                        "blast_radius": blast_radius,
                    }),
                )
                db.add(audit_event)
                await db.commit()
                await db.refresh(incident)

                created_incidents.append(incident)

        return created_incidents
