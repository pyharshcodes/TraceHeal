"""Test suite for Part 5: Isolated Sandbox Execution Engine and Empirical Hypothesis Verification Agent.

Tests:
1. ProcessSandboxRunner lifecycle: dynamic port binding, health checking, and clean teardown.
2. Empirical verification of true hypothesis: reproducing DBPoolExhaustionError in isolated sandbox.
3. Refutation of false hypothesis: non-reproducing workloads marking hypothesis REFUTED.
4. Sandbox REST API endpoints for reproduction and execution run inspection.
"""

import json
import os
import sys
import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport
from typing import Tuple

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.agents.rca_agent import RCAAgent
from backend.app.agents.verification_agent import VerificationAgent
from backend.app.db.models import Hypothesis, Incident
from backend.app.db.session import init_db, engine, Base, async_session_factory
from backend.app.incidents.detector import IncidentDetector
from backend.app.incidents.service import get_incident
from backend.app.main import app
from backend.app.sandbox.runner import ProcessSandboxRunner
from backend.app.schemas.telemetry import SpanCreate
from backend.app.telemetry.ingestion import ingest_spans


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Sets up the database schema before each test and drops tables after."""
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _seed_test_incident(db, trace_id: str = "sbx_seed_trace_101") -> Tuple[Incident, Hypothesis]:
    """Helper that creates an Incident and runs RCA Agent to produce a hypothesis."""
    spans = [
        SpanCreate(
            trace_id=trace_id,
            span_id=f"s_gw_{trace_id}",
            parent_span_id=None,
            service_name="gateway-service",
            operation_name="POST /api/v1/orders/checkout",
            start_time_ns=1700000000000,
            end_time_ns=1700000200000,
            duration_ms=200.0,
            status_code="ERROR",
            http_status_code=502,
            error_message="GatewayCheckoutFailed",
        ),
        SpanCreate(
            trace_id=trace_id,
            span_id=f"s_pay_{trace_id}",
            parent_span_id=f"s_gw_{trace_id}",
            service_name="payment-service",
            operation_name="POST /payments/charge",
            start_time_ns=1700000010000,
            end_time_ns=1700000190000,
            duration_ms=180.0,
            status_code="ERROR",
            http_status_code=500,
            error_message="DBPoolExhaustionError: Timeout acquiring connection from database pool within 100ms",
            attributes_json=json.dumps({"db.pool.exhausted": True, "db.pool.max_size": 2}),
        ),
    ]
    persisted = await ingest_spans(db, spans)
    detector = IncidentDetector()
    inc = (await detector.scan_and_correlate(db, persisted))[0]

    agent = RCAAgent()
    hypotheses = await agent.analyze_incident(db, inc.id)
    return inc, hypotheses[0]


@pytest.mark.asyncio
async def test_process_sandbox_runner_lifecycle():
    """Verifies that ProcessSandboxRunner launches an isolated service, binds to an available

    dynamic port, responds to health pings, and cleanly terminates.
    """
    runner = ProcessSandboxRunner(base_port=9120)
    env = await runner.create_sandbox("payment-service")

    try:
        assert env.is_alive is True
        assert env.port >= 9120
        assert os.path.exists(env.work_dir)

        # Ping isolated sandbox endpoint
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{env.base_url}/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "UP"
            assert data["service"] == "payment-service"
    finally:
        await runner.destroy_sandbox(env)

    # Verify process terminated
    assert env.is_alive is False
    assert not os.path.exists(env.work_dir)


@pytest.mark.asyncio
async def test_empirical_verification_of_true_hypothesis():
    """Tests that the Verification Agent reproduces the DBPoolExhaustionError inside

    the isolated sandbox and marks the hypothesis and incident as VERIFIED.
    """
    async with async_session_factory() as db:
        inc, hyp = await _seed_test_incident(db, "trace_verify_true_201")
        assert hyp.status == "PENDING"
        assert inc.status == "INVESTIGATING"

        agent = VerificationAgent()
        verified_hyp, sandbox_run = await agent.verify_hypothesis(db, hyp.id)

        # 1. Assert reproduction succeeded
        assert sandbox_run.reproduction_verified is True
        assert sandbox_run.status == "SUCCESS"
        assert sandbox_run.port >= 9100
        assert "DBPoolExhaustionError" in str(sandbox_run.reproduction_signature)

        # 2. Assert Hypothesis transitioned to VERIFIED
        assert verified_hyp.status == "VERIFIED"

        # 3. Assert Incident transitioned to VERIFIED
        refreshed_inc = await get_incident(db, inc.id)
        assert refreshed_inc.status == "VERIFIED"

        # 4. Check Audit Trail
        audit_types = [a.event_type for a in refreshed_inc.audit_events]
        assert "HYPOTHESIS_VERIFIED" in audit_types


@pytest.mark.asyncio
async def test_empirical_refutation_of_false_hypothesis():
    """Tests that when a hypothesis presents a non-reproducible or incorrect recipe,

    the Verification Agent marks it as REFUTED and returns the incident to INVESTIGATING.
    """
    async with async_session_factory() as db:
        inc, _ = await _seed_test_incident(db, "trace_refute_false_301")

        # Create false hypothesis with impossible error signature
        false_recipe = {
            "target_service": "payment-service",
            "scenario": "NONE",
            "endpoint": "/payments/charge",
            "concurrency": 1,
            "parameters": {},
            "expected_error_signature": "NonExistentDeadlockSignatureXYZ",
        }
        false_hyp = Hypothesis(
            incident_id=inc.id,
            rank=99,
            title="Non-Reproducible Phantom Bug",
            description="Speculative hypothesis that does not reflect actual failure dynamics.",
            suspect_service="payment-service",
            proposed_cause="Phantom deadlock",
            evidence_summary=f"Reproduction Recipe: {json.dumps(false_recipe)}",
            status="PENDING",
        )
        db.add(false_hyp)
        await db.commit()
        await db.refresh(false_hyp)

        agent = VerificationAgent()
        refuted_hyp, sandbox_run = await agent.verify_hypothesis(db, false_hyp.id)

        # 1. Assert reproduction failed
        assert sandbox_run.reproduction_verified is False
        assert sandbox_run.status == "FAILED"

        # 2. Assert hypothesis REFUTED
        assert refuted_hyp.status == "REFUTED"

        # 3. Assert incident returned to INVESTIGATING
        refreshed_inc = await get_incident(db, inc.id)
        assert refreshed_inc.status == "INVESTIGATING"

        audit_types = [a.event_type for a in refreshed_inc.audit_events]
        assert "HYPOTHESIS_REFUTED" in audit_types


@pytest.mark.asyncio
async def test_sandbox_rest_api_endpoints():
    """Tests the Sandbox REST API endpoints via ASGITransport."""
    async with async_session_factory() as db:
        inc, hyp = await _seed_test_incident(db, "trace_api_sbx_401")
        hyp_id = hyp.id

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger reproduction via API
        resp = await client.post(f"/api/v1/sandbox/reproduce/{hyp_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["hypothesis_id"] == hyp_id
        assert data["hypothesis_status"] == "VERIFIED"
        assert data["reproduction_verified"] is True
        assert data["port"] >= 9100
        run_id = data["sandbox_run_id"]

        # 2. Query sandbox run details
        run_resp = await client.get(f"/api/v1/sandbox/runs/{run_id}")
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["id"] == run_id
        assert run_data["service_name"] == "payment-service"
        assert run_data["reproduction_verified"] is True

        # 3. List all sandbox runs
        list_resp = await client.get("/api/v1/sandbox/runs")
        assert list_resp.status_code == 200
        runs_list = list_resp.json()
        assert any(r["id"] == run_id for r in runs_list)
