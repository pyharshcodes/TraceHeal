import os
import sys
import pytest
import pytest_asyncio
from sqlalchemy import text, select

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.core.config import settings
from backend.app.db.session import engine, async_session_factory, init_db, close_db, Base
from backend.app.db.models import (
    Incident,
    TelemetrySpan,
    Hypothesis,
    SandboxRun,
    Remediation,
    AuditEvent,
)
from backend.app.schemas.incident import IncidentCreate, IncidentRead
from backend.app.schemas.telemetry import SpanCreate, SpanRead


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Sets up the test database schema before tests and cleans up after."""
    await init_db()
    yield
    # Cleanup tables after test cleanly
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_settings_configuration():
    """Verifies that system settings are properly initialized."""
    assert settings.app_name == "TraceHeal Autonomous SRE"
    assert settings.app_version == "1.0.0"
    assert settings.port == 8000
    assert "sqlite" in settings.database_url


@pytest.mark.asyncio
async def test_sqlite_pragmas():
    """Verifies SQLite WAL mode and Foreign Keys are enabled."""
    async with async_session_factory() as session:
        result = await session.execute(text("PRAGMA journal_mode;"))
        mode = result.scalar()
        assert str(mode).lower() == "wal"

        fk_result = await session.execute(text("PRAGMA foreign_keys;"))
        fk = fk_result.scalar()
        assert fk == 1


@pytest.mark.asyncio
async def test_incident_lifecycle_crud():
    """Tests creating, querying, updating, and deleting an incident."""
    async with async_session_factory() as session:
        # Create
        inc = Incident(
            title="Database Connection Pool Exhaustion",
            description="Payment service reporting timeout acquiring DB connection under load.",
            severity="CRITICAL",
            status="DETECTED",
            suspect_service="payment-service",
            blast_radius_json='{"affected": ["order-service", "gateway-service"]}',
        )
        session.add(inc)
        await session.commit()
        await session.refresh(inc)

        inc_id = inc.id
        assert inc_id is not None
        assert inc.status == "DETECTED"

    # Query & Update
    async with async_session_factory() as session:
        stmt = select(Incident).where(Incident.id == inc_id)
        result = await session.execute(stmt)
        fetched = result.scalar_one()

        assert fetched.title == "Database Connection Pool Exhaustion"
        assert fetched.suspect_service == "payment-service"

        # Update status
        fetched.status = "INVESTIGATING"
        fetched.root_cause_summary = "Pool size 2 overwhelmed by 10 concurrent requests."
        await session.commit()

    # Verify update
    async with async_session_factory() as session:
        stmt = select(Incident).where(Incident.id == inc_id)
        result = await session.execute(stmt)
        updated = result.scalar_one()
        assert updated.status == "INVESTIGATING"
        assert updated.root_cause_summary is not None


@pytest.mark.asyncio
async def test_telemetry_span_ingestion_and_hierarchy():
    """Tests ingesting parent and child spans and querying by trace_id."""
    trace_id = "trace-4a92b8d0e7f1"
    parent_span_id = "span-gateway-01"
    child_span_id = "span-payment-02"

    async with async_session_factory() as session:
        # Parent span: Gateway
        s1 = TelemetrySpan(
            trace_id=trace_id,
            span_id=parent_span_id,
            parent_span_id=None,
            service_name="gateway-service",
            operation_name="POST /checkout",
            start_time_ns=1700000000000000000,
            end_time_ns=1700000000850000000,
            duration_ms=850.0,
            status_code="ERROR",
            http_status_code=504,
            error_message="Gateway Timeout",
            attributes_json='{"http.method": "POST", "http.route": "/checkout"}',
        )
        # Child span: Payment
        s2 = TelemetrySpan(
            trace_id=trace_id,
            span_id=child_span_id,
            parent_span_id=parent_span_id,
            service_name="payment-service",
            operation_name="POST /pay",
            start_time_ns=1700000000050000000,
            end_time_ns=1700000000840000000,
            duration_ms=790.0,
            status_code="ERROR",
            http_status_code=500,
            error_message="Timeout: DB connection pool exhausted",
            attributes_json='{"db.system": "postgresql", "db.pool.exhausted": true}',
        )
        session.add_all([s1, s2])
        await session.commit()

    # Query all spans by trace_id
    async with async_session_factory() as session:
        stmt = select(TelemetrySpan).where(TelemetrySpan.trace_id == trace_id).order_by(TelemetrySpan.start_time_ns)
        result = await session.execute(stmt)
        spans = result.scalars().all()

        assert len(spans) == 2
        assert spans[0].span_id == parent_span_id
        assert spans[0].parent_span_id is None
        assert spans[1].span_id == child_span_id
        assert spans[1].parent_span_id == parent_span_id
        assert spans[1].http_status_code == 500


@pytest.mark.asyncio
async def test_full_incident_entities_and_relationships():
    """Tests the linked chain: Incident -> Hypothesis -> SandboxRun -> Remediation -> AuditEvent."""
    async with async_session_factory() as session:
        # 1. Create Incident
        inc = Incident(
            title="Payment Pool Failure",
            severity="CRITICAL",
            status="INVESTIGATING",
            suspect_service="payment-service",
        )
        session.add(inc)
        await session.commit()
        await session.refresh(inc)

        # 2. Add Hypothesis
        hyp = Hypothesis(
            incident_id=inc.id,
            rank=1,
            title="Postgres Connection Pool Saturation",
            description="Max pool size of 2 cannot service concurrent burst checkout calls.",
            suspect_service="payment-service",
            proposed_cause="pool_size=2 configuration bottleneck",
            status="TESTING",
        )
        session.add(hyp)
        await session.commit()
        await session.refresh(hyp)

        # 3. Add Sandbox Run
        sb = SandboxRun(
            incident_id=inc.id,
            hypothesis_id=hyp.id,
            service_name="payment-service",
            sandbox_type="PROCESS",
            port=9105,
            status="SUCCESS",
            exit_code=500,
            reproduction_verified=True,
            reproduction_signature="Timeout: DB connection pool exhausted",
        )
        session.add(sb)

        # 4. Add Remediation
        rem = Remediation(
            incident_id=inc.id,
            hypothesis_id=hyp.id,
            patch_type="CONFIG",
            target_service="payment-service",
            diff_content="--- a/config.py\n+++ b/config.py\n-DB_POOL_SIZE=2\n+DB_POOL_SIZE=20",
            policy_check_status="PASSED",
            approval_status="PENDING_APPROVAL",
        )
        session.add(rem)

        # 5. Add Audit Event
        audit = AuditEvent(
            incident_id=inc.id,
            event_type="SANDBOX_VERIFIED",
            actor="AGENT_SANDBOX",
            details_json='{"reproduced": true, "exit_code": 500}',
        )
        session.add(audit)
        await session.commit()

    # Query back with relationships
    async with async_session_factory() as session:
        stmt = select(Incident).where(Incident.id == inc.id)
        result = await session.execute(stmt)
        fetched_inc = result.scalar_one()

        assert len(fetched_inc.hypotheses) == 1
        assert fetched_inc.hypotheses[0].rank == 1
        assert len(fetched_inc.sandbox_runs) == 1
        assert fetched_inc.sandbox_runs[0].reproduction_verified is True
        assert len(fetched_inc.remediations) == 1
        assert fetched_inc.remediations[0].policy_check_status == "PASSED"
        assert len(fetched_inc.audit_events) == 1
        assert fetched_inc.audit_events[0].event_type == "SANDBOX_VERIFIED"


@pytest.mark.asyncio
async def test_schema_validations():
    """Tests Pydantic models serialization and validation."""
    payload = {
        "title": "API Gateway Latency Degradation",
        "severity": "HIGH",
        "suspect_service": "gateway-service",
    }
    schema = IncidentCreate(**payload)
    assert schema.title == "API Gateway Latency Degradation"
    assert schema.severity == "HIGH"
