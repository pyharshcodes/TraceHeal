"""Chaos injection, cluster control, and incident simulation API endpoints."""

import time
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

import json
from backend.app.core.auth import UserProfile, UserRole, require_role
from backend.app.db.session import get_db
from backend.app.events.hooks import (
    emit_agent_action,
    emit_agent_thought,
    emit_incident_state_change,
    emit_telemetry_spike,
)
from backend.app.incidents.detector import IncidentDetector
from backend.app.schemas.telemetry import SpanCreate
from backend.app.telemetry.ingestion import ingest_spans
from target_services.chaos import ChaosEngine, ChaosScenario

router = APIRouter(prefix="/chaos", tags=["Chaos & Cluster Control"])
chaos_engine = ChaosEngine()
detector = IncidentDetector()


class ChaosInjectRequest(BaseModel):
    scenario: str = Field(..., description="Chaos scenario name (e.g. DB_POOL_EXHAUSTION, LATENCY_SPIKE, DEADLOCK, INVENTORY_OUTAGE)")
    target_service: str = Field(default="payment-service", description="Target service name")
    params: Dict[str, Any] = Field(default_factory=dict, description="Scenario-specific parameters")


class SimulateIncidentRequest(BaseModel):
    fault_type: str = Field(default="DB_POOL_EXHAUSTION", description="Fault type to simulate")
    target_service: str = Field(default="payment-service", description="Service to fail")
    trace_count: int = Field(default=3, description="Number of error traces to generate")
    force_new: bool = Field(default=True, description="Force create a fresh incident for simulation")


@router.get("/status")
async def get_cluster_status():
    """Queries health and status across all microservice cluster nodes."""
    try:
        status = await chaos_engine.get_cluster_status()
        return {
            "cluster_connected": True,
            "services": status,
        }
    except Exception as exc:
        return {
            "cluster_connected": False,
            "services": {
                "gateway-service": {"status": "UNKNOWN", "port": 8080},
                "auth-service": {"status": "UNKNOWN", "port": 8084},
                "order-service": {"status": "UNKNOWN", "port": 8081},
                "payment-service": {"status": "UNKNOWN", "port": 8082},
                "inventory-service": {"status": "UNKNOWN", "port": 8083},
                "notification-service": {"status": "UNKNOWN", "port": 8085},
            },
            "error": str(exc),
        }


@router.get("/ping/{service_name}")
async def ping_service_node(service_name: str):
    """Pings a specific microservice node and measures response latency."""
    import httpx
    ports = {
        "gateway-service": 8080,
        "order-service": 8081,
        "payment-service": 8082,
        "inventory-service": 8083,
        "auth-service": 8084,
        "notification-service": 8085,
    }
    port = ports.get(service_name, 8080)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(f"http://127.0.0.1:{port}/health")
            duration_ms = round((time.time() - t0) * 1000, 1)
            return {
                "service": service_name,
                "port": port,
                "status": "UP" if resp.status_code == 200 else "DEGRADED",
                "http_status": resp.status_code,
                "latency_ms": duration_ms,
            }
    except Exception:
        # Fallback simulated response
        return {
            "service": service_name,
            "port": port,
            "status": "UP",
            "http_status": 200,
            "latency_ms": round(10.0 + (hash(service_name) % 15), 1),
            "simulated": True,
        }


@router.post("/inject")
async def inject_chaos(
    req: ChaosInjectRequest,
    user: UserProfile = Depends(require_role(UserRole.SRE_OPERATOR)),
):
    """Programmatically injects a chaos scenario into a microservice and emits observability events."""
    try:
        scenario_enum = ChaosScenario(req.scenario)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scenario '{req.scenario}'. Supported: {[s.value for s in ChaosScenario]}",
        )

    # Emit telemetry spike and agent notification
    await emit_telemetry_spike(
        service_name=req.target_service,
        error_rate=1.0,
        duration_ms=2500.0,
        error_message=f"Chaos injected: {req.scenario}",
    )
    await emit_agent_action(
        incident_id="SYSTEM",
        agent_name="ChaosEngine",
        action=f"inject_failure: {req.scenario} on {req.target_service}",
        details={"scenario": req.scenario, "params": req.params},
    )

    try:
        res = await chaos_engine.inject(scenario_enum, target_service=req.target_service, **req.params)
        return {
            "status": "INJECTED",
            "scenario": req.scenario,
            "target_service": req.target_service,
            "result": res,
        }
    except Exception as exc:
        # If services aren't running in process, still acknowledge event for UI dashboard simulation
        return {
            "status": "SIMULATED",
            "scenario": req.scenario,
            "target_service": req.target_service,
            "note": f"Chaos registered & SSE broadcasted (target service offline: {exc})",
        }


@router.post("/reset")
async def reset_chaos():
    """Resets all chaos injections across target services."""
    await emit_agent_action(
        incident_id="SYSTEM",
        agent_name="ChaosEngine",
        action="reset_cluster",
        details={"action": "baseline_restored"},
    )
    try:
        res = await chaos_engine.reset_all()
        return {"status": "RESET_SUCCESS", "services": res}
    except Exception as exc:
        return {"status": "RESET_SIMULATED", "note": str(exc)}


@router.post("/simulate-incident")
async def simulate_incident(req: SimulateIncidentRequest, db: AsyncSession = Depends(get_db)):
    """Simulates an outage scenario with ingested spans, automated detection, and SSE event streaming."""
    from sqlalchemy import select
    from backend.app.db.models import Incident

    if req.force_new:
        stmt = (
            select(Incident)
            .where(Incident.suspect_service == req.target_service)
            .where(Incident.status.notin_(["RESOLVED", "CLOSED"]))
        )
        res = await db.execute(stmt)
        active_incs = res.scalars().all()
        for ai in active_incs:
            ai.status = "CLOSED"
        if active_incs:
            await db.commit()

    now_ms = time.time() * 1000.0
    now_ns = int(now_ms * 1_000_000)
    spans_to_ingest = []
    trace_ids = []

    # Emit agent thought starting simulation
    await emit_agent_thought(
        incident_id="SIMULATION",
        agent_name="AutonomousObserver",
        thought=f"Detected anomaly pattern on {req.target_service}: sudden surge in {req.fault_type}. Correlating spans...",
    )

    for i in range(req.trace_count):
        trace_id = f"sim-{uuid.uuid4().hex[:12]}"
        gw_span_id = uuid.uuid4().hex[:8]
        order_span_id = uuid.uuid4().hex[:8]
        pay_span_id = uuid.uuid4().hex[:8]
        trace_ids.append(trace_id)

        # 1. Gateway Span (HTTP 500)
        spans_to_ingest.append(
            SpanCreate(
                trace_id=trace_id,
                span_id=gw_span_id,
                parent_span_id=None,
                service_name="gateway-service",
                operation_name="POST /api/v1/orders",
                start_time_ns=now_ns + int(i * 20_000_000),
                end_time_ns=now_ns + int((i * 20 + 1200.0) * 1_000_000),
                duration_ms=1200.0,
                status_code="ERROR",
                http_status_code=500,
                error_message="Downstream service failure",
                attributes_json=json.dumps({"http.method": "POST", "http.route": "/api/v1/orders"}),
            )
        )

        # 2. Order Span (HTTP 500)
        spans_to_ingest.append(
            SpanCreate(
                trace_id=trace_id,
                span_id=order_span_id,
                parent_span_id=gw_span_id,
                service_name="order-service",
                operation_name="POST /orders",
                start_time_ns=now_ns + int((i * 20 + 5) * 1_000_000),
                end_time_ns=now_ns + int((i * 20 + 1195.0) * 1_000_000),
                duration_ms=1190.0,
                status_code="ERROR",
                http_status_code=500,
                error_message="Downstream service failure",
                attributes_json=json.dumps({"order_id": f"ord-{i}"}),
            )
        )

        # 3. Target Service Span (Failure Origin)
        if req.target_service == "payment-service":
            op_name = "POST /payments/charge"
            err_msg = f"Connection pool exhausted: {req.fault_type}"
        elif req.target_service == "inventory-service":
            op_name = "POST /inventory/reserve"
            err_msg = f"Inventory lock timeout: {req.fault_type}"
        elif req.target_service == "auth-service":
            op_name = "POST /auth/verify"
            err_msg = f"JWKS token verification failed: {req.fault_type}"
        elif req.target_service == "notification-service":
            op_name = "POST /notifications/send"
            err_msg = f"Queue overflow dead-letter: {req.fault_type}"
        else:
            op_name = f"POST /{req.target_service}/exec"
            err_msg = f"Service failure: {req.fault_type}"

        spans_to_ingest.append(
            SpanCreate(
                trace_id=trace_id,
                span_id=pay_span_id,
                parent_span_id=order_span_id,
                service_name=req.target_service,
                operation_name=op_name,
                start_time_ns=now_ns + int((i * 20 + 10) * 1_000_000),
                end_time_ns=now_ns + int((i * 20 + 1190.0) * 1_000_000),
                duration_ms=1180.0,
                status_code="ERROR",
                http_status_code=500,
                error_message=err_msg,
                attributes_json=json.dumps({
                    "error.type": "ConnectionTimeoutError" if req.fault_type == "DB_POOL_EXHAUSTION" else "ServiceUnavailableError",
                    "fault": req.fault_type,
                    "target": req.target_service,
                }),
            )
        )

    # Ingest spans into database
    ingested_models = await ingest_spans(db, spans_to_ingest)

    # Detect incident
    incidents = await detector.scan_and_correlate(db, ingested_models)

    # Notify via SSE
    await emit_telemetry_spike(
        service_name=req.target_service,
        error_rate=1.0,
        duration_ms=1200.0,
        error_message=f"Cascading error storm: {req.fault_type}",
    )

    incident_summary = None
    if incidents:
        inc = incidents[0]
        incident_summary = {
            "id": inc.id,
            "title": inc.title,
            "severity": inc.severity,
            "status": inc.status,
            "suspect_service": inc.suspect_service,
        }
        await emit_incident_state_change(
            incident_id=inc.id,
            from_status="NONE",
            to_status=inc.status,
            reason=f"Auto-detected {req.fault_type} via critical path correlation",
        )
        await emit_agent_thought(
            incident_id=inc.id,
            agent_name="RCADiagnosticAgent",
            thought=f"Incident {inc.id} created. Root-cause hypothesis: {req.fault_type} in {req.target_service}. Ready for sandbox reproduction.",
        )

    return {
        "status": "INCIDENT_SIMULATED",
        "fault_type": req.fault_type,
        "target_service": req.target_service,
        "traces_generated": trace_ids,
        "incident": incident_summary,
    }
