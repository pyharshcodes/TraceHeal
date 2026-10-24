"""Test suite for Part 4: Autonomous Incident Detection, Alert Correlation Engine,

and RCA Hypothesis Generation Agent.
"""

import json
import os
import sys
import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.agents.rca_agent import RCAAgent
from backend.app.db.session import init_db, engine, Base, async_session_factory
from backend.app.incidents.detector import IncidentDetector
from backend.app.incidents.service import (
    get_incident,
    transition_incident_status,
)
from backend.app.main import app
from backend.app.schemas.telemetry import SpanCreate
from backend.app.telemetry.ingestion import ingest_spans


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Sets up the database schema before each test and drops tables after."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _create_cascading_failure_spans(trace_id: str = "trace_cascade_4001") -> list:
    """Helper that generates a 3-tier cascade failure: Gateway (502) -> Order (502) -> Payment (500)."""
    return [
        SpanCreate(
            trace_id=trace_id,
            span_id=f"s_gw_{trace_id}",
            parent_span_id=None,
            service_name="gateway-service",
            operation_name="POST /api/v1/orders/checkout",
            start_time_ns=1700000000000,
            end_time_ns=1700000210000,
            duration_ms=210.0,
            status_code="ERROR",
            http_status_code=502,
            error_message="GatewayCheckoutFailed: downstream 502",
        ),
        SpanCreate(
            trace_id=trace_id,
            span_id=f"s_ord_{trace_id}",
            parent_span_id=f"s_gw_{trace_id}",
            service_name="order-service",
            operation_name="POST /orders/process",
            start_time_ns=1700000010000,
            end_time_ns=1700000200000,
            duration_ms=190.0,
            status_code="ERROR",
            http_status_code=502,
            error_message="OrderFailed: downstream payment returned 500",
        ),
        SpanCreate(
            trace_id=trace_id,
            span_id=f"s_pay_{trace_id}",
            parent_span_id=f"s_ord_{trace_id}",
            service_name="payment-service",
            operation_name="POST /payments/charge",
            start_time_ns=1700000020000,
            end_time_ns=1700000190000,
            duration_ms=170.0,
            status_code="ERROR",
            http_status_code=500,
            error_message="DBPoolExhaustionError: Timeout acquiring connection from database pool within 100ms (active: 2, max: 2)",
            attributes_json=json.dumps({"db.pool.exhausted": True, "db.pool.max_size": 2, "active_connections": 2}),
        ),
    ]


@pytest.mark.asyncio
async def test_incident_detection_and_correlation():
    """Tests that the IncidentDetector groups cascading errors across multiple

    traces into a single consolidated Incident with blast radius computation.
    """
    async with async_session_factory() as db:
        # Ingest 2 traces with the same cascade failure
        spans_t1 = await _create_cascading_failure_spans("trace_401")
        spans_t2 = await _create_cascading_failure_spans("trace_402")
        all_spans = await ingest_spans(db, spans_t1 + spans_t2)

        # Detect incidents
        detector = IncidentDetector()
        incidents = await detector.scan_and_correlate(db, all_spans)

        # Must correlate into exactly ONE incident
        assert len(incidents) == 1
        inc = incidents[0]

        assert inc.suspect_service == "payment-service"
        assert inc.severity == "CRITICAL"
        assert inc.status == "DETECTED"
        assert "payment-service" in inc.title

        # Check Blast Radius
        blast = json.loads(inc.blast_radius_json)
        assert "payment-service" in blast["affected_services"]
        assert "order-service" in blast["affected_services"]
        assert "gateway-service" in blast["affected_services"]
        assert blast["correlated_traces_count"] == 2
        assert "DBPoolExhaustionError" in blast["primary_error_signature"]


@pytest.mark.asyncio
async def test_rca_agent_hypothesis_generation():
    """Tests that the RCA Agent investigates an incident, performs causal reasoning,

    and synthesizes ranked hypotheses with reproduction recipes.
    """
    async with async_session_factory() as db:
        # 1. Setup Incident with spans
        spans = await _create_cascading_failure_spans("trace_rca_501")
        persisted_spans = await ingest_spans(db, spans)

        detector = IncidentDetector()
        incidents = await detector.scan_and_correlate(db, persisted_spans)
        inc = incidents[0]

        # 2. Invoke RCA Agent
        agent = RCAAgent()
        hypotheses = await agent.analyze_incident(db, inc.id)

        assert len(hypotheses) >= 1
        h1 = hypotheses[0]

        assert h1.rank == 1
        assert "Connection Pool" in h1.title
        assert h1.suspect_service == "payment-service"
        assert h1.suspect_component == "SimulatedDatabasePool"
        assert "insufficient" in h1.proposed_cause or "burst" in h1.proposed_cause
        assert "Reproduction Recipe" in h1.evidence_summary

        # Check Incident State Updated
        refreshed_inc = await get_incident(db, inc.id)
        assert refreshed_inc.status == "INVESTIGATING"
        assert refreshed_inc.root_cause_summary is not None
        assert len(refreshed_inc.hypotheses) >= 1

        # Check Audit Trail
        audit_types = [a.event_type for a in refreshed_inc.audit_events]
        assert "INCIDENT_DETECTED" in audit_types
        assert "HYPOTHESES_GENERATED" in audit_types


@pytest.mark.asyncio
async def test_incident_state_machine_validation():
    """Tests that incident state machine enforces legal progression and prevents illegal jumps."""
    async with async_session_factory() as db:
        # Setup incident
        spans = await _create_cascading_failure_spans("trace_sm_601")
        persisted = await ingest_spans(db, spans)
        detector = IncidentDetector()
        inc = (await detector.scan_and_correlate(db, persisted))[0]
        assert inc.status == "DETECTED"

        # 1. Illegal transition: DETECTED -> REMEDIATED (cannot skip investigation & reproduction)
        with pytest.raises(ValueError, match="Illegal incident transition"):
            await transition_incident_status(db, inc.id, "REMEDIATED")

        # 2. Legal progression: DETECTED -> INVESTIGATING -> REPRODUCING -> VERIFIED -> REMEDIATED -> RESOLVED -> CLOSED
        await transition_incident_status(db, inc.id, "INVESTIGATING")
        inc = await get_incident(db, inc.id)
        assert inc.status == "INVESTIGATING"

        await transition_incident_status(db, inc.id, "REPRODUCING")
        inc = await get_incident(db, inc.id)
        assert inc.status == "REPRODUCING"

        await transition_incident_status(db, inc.id, "VERIFIED")
        inc = await get_incident(db, inc.id)
        assert inc.status == "VERIFIED"

        await transition_incident_status(db, inc.id, "REMEDIATED")
        inc = await get_incident(db, inc.id)
        assert inc.status == "REMEDIATED"

        await transition_incident_status(db, inc.id, "RESOLVED")
        inc = await get_incident(db, inc.id)
        assert inc.status == "RESOLVED"

        await transition_incident_status(db, inc.id, "CLOSED")
        inc = await get_incident(db, inc.id)
        assert inc.status == "CLOSED"


@pytest.mark.asyncio
async def test_incidents_rest_api():
    """Tests the complete Incidents REST API workflow via ASGITransport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest failure spans
        spans_payload = [s.model_dump() for s in await _create_cascading_failure_spans("trace_api_701")]
        ingest_res = await client.post("/api/v1/telemetry/spans", json=spans_payload)
        assert ingest_res.status_code == 201

        # 2. Trigger detection
        detect_res = await client.post("/api/v1/incidents/detect")
        assert detect_res.status_code == 200
        detect_data = detect_res.json()
        assert detect_data["detected_count"] >= 1
        incident_id = detect_data["incidents"][0]["id"]

        # 3. List incidents
        list_res = await client.get("/api/v1/incidents")
        assert list_res.status_code == 200
        assert any(i["id"] == incident_id for i in list_res.json())

        # 4. Trigger RCA analysis
        rca_res = await client.post(f"/api/v1/incidents/{incident_id}/analyze")
        assert rca_res.status_code == 200
        assert rca_res.json()["hypotheses_generated"] >= 1

        # 5. Fetch full incident details
        detail_res = await client.get(f"/api/v1/incidents/{incident_id}")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert detail_data["status"] == "INVESTIGATING"
        assert len(detail_data["hypotheses"]) >= 1
        assert "affected_services" in detail_data["blast_radius"]
        assert len(detail_data["audit_events"]) >= 2

        # 6. Transition status via API
        patch_res = await client.patch(
            f"/api/v1/incidents/{incident_id}/status",
            json={"status": "REPRODUCING", "actor": "TEST_RUNNER", "reason": "Moving to sandbox reproduction"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["status"] == "REPRODUCING"
