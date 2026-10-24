"""Telemetry API endpoints for OpenTelemetry ingestion, trace DAGs, and topology."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.schemas.telemetry import SpanCreate, SpanRead
from backend.app.telemetry.critical_path import identify_failure_origin, identify_latency_bottleneck
from backend.app.telemetry.ingestion import (
    get_all_spans,
    get_recent_trace_summaries,
    get_recent_traces,
    get_spans_by_incident,
    get_spans_by_trace,
    ingest_spans,
)
from backend.app.telemetry.service_graph import build_service_dependency_graph
from backend.app.telemetry.trace_graph import build_trace_tree

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


@router.post("/spans", status_code=status.HTTP_201_CREATED)
async def ingest_telemetry_spans(
    spans: List[SpanCreate],
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Ingests a batch of distributed tracing spans from OpenTelemetry collectors."""
    if not spans:
        return {"ingested_count": 0, "status": "EMPTY_BATCH"}

    persisted = await ingest_spans(db, spans)
    return {
        "ingested_count": len(persisted),
        "status": "INGESTED",
        "trace_ids": list({s.trace_id for s in spans}),
    }


@router.get("/spans", response_model=List[SpanRead])
async def query_spans(
    incident_id: Optional[str] = Query(None),
    service_name: Optional[str] = Query(None),
    trace_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieves spans filtered by incident_id, trace_id, or service_name."""
    if incident_id:
        return await get_spans_by_incident(db, incident_id=incident_id, limit=limit)
    if trace_id:
        return await get_spans_by_trace(db, trace_id=trace_id)
    return await get_all_spans(db, limit=limit, service_name=service_name)


@router.get("/spans/{trace_id}", response_model=List[SpanRead])
async def get_trace_spans(
    trace_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieves all flat spans for a specific trace_id."""
    spans = await get_spans_by_trace(db, trace_id)
    if not spans:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No spans found for trace_id '{trace_id}'",
        )
    return spans


@router.get("/traces/{trace_id}")
async def get_trace_details(
    trace_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Retrieves complete trace details including flat spans, DAG tree, and failure origin."""
    spans = await get_spans_by_trace(db, trace_id)
    if not spans:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No spans found for trace_id '{trace_id}'",
        )

    roots = build_trace_tree(spans)
    bottleneck = identify_latency_bottleneck(spans)
    failure_origin = identify_failure_origin(spans)

    return {
        "trace_id": trace_id,
        "total_spans": len(spans),
        "spans": [
            {
                "id": s.id,
                "incident_id": s.incident_id,
                "trace_id": s.trace_id,
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "service_name": s.service_name,
                "operation_name": s.operation_name,
                "start_time_ns": s.start_time_ns,
                "end_time_ns": s.end_time_ns,
                "duration_ms": s.duration_ms,
                "status_code": s.status_code,
                "http_status_code": s.http_status_code,
                "error_message": s.error_message,
                "attributes_json": s.attributes_json,
            }
            for s in spans
        ],
        "tree": [r.to_dict() for r in roots],
        "latency_bottleneck": bottleneck,
        "failure_origin": failure_origin.to_dict(),
    }


@router.get("/traces/{trace_id}/tree")
async def get_trace_tree(
    trace_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Reconstructs the hierarchical DAG call tree for a specific trace_id."""
    spans = await get_spans_by_trace(db, trace_id)
    if not spans:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No spans found for trace_id '{trace_id}'",
        )

    roots = build_trace_tree(spans)
    bottleneck = identify_latency_bottleneck(spans)
    failure_origin = identify_failure_origin(spans)

    return {
        "trace_id": trace_id,
        "total_spans": len(spans),
        "tree": [r.to_dict() for r in roots],
        "latency_bottleneck": bottleneck,
        "failure_origin": failure_origin.to_dict(),
    }


@router.get("/traces/{trace_id}/failure-origin")
async def get_trace_failure_origin(
    trace_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Pinpoints the deepest causal failure origin span in the trace."""
    spans = await get_spans_by_trace(db, trace_id)
    if not spans:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No spans found for trace_id '{trace_id}'",
        )

    report = identify_failure_origin(spans)
    return report.to_dict()


@router.get("/traces")
async def list_recent_traces(
    limit: int = Query(default=30, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Lists recent traces with both raw IDs and enriched summaries."""
    recent_ids = await get_recent_traces(db, limit=limit)
    summaries = await get_recent_trace_summaries(db, limit=limit)
    return {
        "traces": recent_ids,
        "trace_summaries": summaries,
        "count": len(recent_ids),
    }


@router.get("/topology")
async def get_service_topology(
    limit: int = Query(default=500, ge=10, le=2000),
    db: AsyncSession = Depends(get_db_session),
) -> Dict[str, Any]:
    """Infers the dynamic service dependency topology from recently recorded spans."""
    spans = await get_all_spans(db, limit=limit)
    return build_service_dependency_graph(spans)
