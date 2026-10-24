"""Telemetry ingestion engine for OpenTelemetry distributed spans."""

from typing import List, Optional
from sqlalchemy import select, desc, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import TelemetrySpan
from backend.app.schemas.telemetry import SpanCreate, SpanRead


async def ingest_spans(db: AsyncSession, spans: List[SpanCreate]) -> List[TelemetrySpan]:
    """Persists a batch of telemetry spans in an atomic database transaction."""
    db_spans = []
    for s in spans:
        db_span = TelemetrySpan(
            incident_id=s.incident_id,
            trace_id=s.trace_id,
            span_id=s.span_id,
            parent_span_id=s.parent_span_id,
            service_name=s.service_name,
            operation_name=s.operation_name,
            start_time_ns=s.start_time_ns,
            end_time_ns=s.end_time_ns,
            duration_ms=s.duration_ms,
            status_code=s.status_code,
            http_status_code=s.http_status_code,
            error_message=s.error_message,
            attributes_json=s.attributes_json,
            events_json=s.events_json,
        )
        db_spans.append(db_span)

    db.add_all(db_spans)
    await db.commit()
    for s in db_spans:
        await db.refresh(s)
    return db_spans


async def get_spans_by_trace(db: AsyncSession, trace_id: str) -> List[TelemetrySpan]:
    """Retrieves all spans belonging to a trace, ordered by start time."""
    stmt = (
        select(TelemetrySpan)
        .where(TelemetrySpan.trace_id == trace_id)
        .order_by(TelemetrySpan.start_time_ns)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_recent_traces(db: AsyncSession, limit: int = 50) -> List[str]:
    """Retrieves distinct trace IDs ordered by most recent span."""
    stmt = (
        select(TelemetrySpan.trace_id)
        .distinct()
        .order_by(desc(TelemetrySpan.id))
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_spans_by_incident(
    db: AsyncSession,
    incident_id: str,
    limit: int = 50,
) -> List[TelemetrySpan]:
    """Retrieves all spans linked to an incident, ordered by execution start time."""
    stmt = (
        select(TelemetrySpan)
        .where(TelemetrySpan.incident_id == incident_id)
        .order_by(TelemetrySpan.start_time_ns)
        .limit(limit)
    )
    result = await db.execute(stmt)
    spans = list(result.scalars().all())
    if not spans:
        # Fallback to recent spans from the system if direct tagging was not yet assigned
        stmt_fallback = select(TelemetrySpan).order_by(desc(TelemetrySpan.id)).limit(limit)
        res_fb = await db.execute(stmt_fallback)
        spans = list(res_fb.scalars().all())
    return spans


async def get_recent_trace_summaries(
    db: AsyncSession,
    limit: int = 30,
) -> List[dict]:
    """Retrieves enriched summaries for recent traces for visualization in the trace explorer."""
    recent_ids = await get_recent_traces(db, limit=limit)
    summaries = []
    for tid in recent_ids:
        spans = await get_spans_by_trace(db, tid)
        if not spans:
            continue
        err_count = sum(1 for s in spans if s.status_code == "ERROR" or (s.http_status_code and s.http_status_code >= 500))
        max_duration = max((s.duration_ms or 0) for s in spans) if spans else 0
        services = list(dict.fromkeys(s.service_name for s in spans if s.service_name))
        summaries.append({
            "trace_id": tid,
            "spans_count": len(spans),
            "error_count": err_count,
            "duration_ms": max_duration,
            "services": services,
            "root_service": spans[0].service_name if spans else "unknown",
            "start_time_ns": spans[0].start_time_ns if spans else 0,
        })
    return summaries


async def get_all_spans(
    db: AsyncSession,
    limit: int = 200,
    service_name: Optional[str] = None,
    status_code: Optional[str] = None,
) -> List[TelemetrySpan]:
    stmt = select(TelemetrySpan)
    if service_name:
        stmt = stmt.where(TelemetrySpan.service_name == service_name)
    if status_code:
        stmt = stmt.where(TelemetrySpan.status_code == status_code)
    stmt = stmt.order_by(desc(TelemetrySpan.id)).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
