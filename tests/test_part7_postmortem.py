"""Tests for Part 7: Post-Incident Dossier, PR Generator & Postmortem Engine."""

import json
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.db.models import AuditEvent, Hypothesis, Incident, Remediation, SandboxRun
from backend.app.db.session import async_session_factory, init_db
from backend.app.main import app
from backend.app.postmortem.generator import PostmortemGenerator
from backend.app.postmortem.pr_generator import PullRequestGenerator
from backend.app.postmortem.recovery_validator import RecoveryValidator
from backend.app.postmortem.service import PostmortemService
from target_services.cluster import ServiceCluster


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()


@pytest_asyncio.fixture(scope="module")
async def cluster():
    """Starts the service cluster once for Part 7 tests and stops it afterwards if not already running."""
    import httpx
    already_running = False
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            r = await client.get("http://127.0.0.1:8080/health")
            if r.status_code == 200:
                already_running = True
    except Exception:
        pass

    if already_running:
        yield None
        return

    svc_cluster = ServiceCluster()
    await svc_cluster.start()
    ready = await svc_cluster.wait_until_ready(timeout=10.0)
    assert ready is True, "Service cluster failed to reach ready state within 10s"
    yield svc_cluster
    await svc_cluster.stop()


@pytest.mark.asyncio
async def test_post_remediation_recovery_validator(cluster):
    """Validates cluster health post-remediation and state transition from REMEDIATED to RESOLVED."""
    async with async_session_factory() as session:
        incident = Incident(
            title="Payment Outage Under Load",
            severity="CRITICAL",
            status="REMEDIATED",
            suspect_service="payment-service",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        validator = RecoveryValidator()
        res = await validator.validate_recovery(
            db=session,
            incident_id=incident.id,
            target_service_url="http://127.0.0.1:8082",
            test_requests=3,
        )

        assert res.status == "RESOLVED"
        assert res.recovery_confirmed is True
        assert res.baseline_transactions_succeeded == 3
        assert res.baseline_transactions_failed == 0

        # Verify incident status advanced to RESOLVED
        await session.refresh(incident)
        assert incident.status == "RESOLVED"
        assert incident.resolved_at is not None

        # Verify audit trail
        stmt = select(AuditEvent).where(
            AuditEvent.incident_id == incident.id,
            AuditEvent.event_type == "RECOVERY_VALIDATED"
        )
        audits = (await session.execute(stmt)).scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_automated_postmortem_markdown_and_metrics():
    """Validates generation of comprehensive Markdown postmortem with MTTD/MTTR and timelines."""
    async with async_session_factory() as session:
        incident = Incident(
            title="Database Connection Pool Depletion Outage",
            severity="CRITICAL",
            status="RESOLVED",
            suspect_service="payment-service",
            root_cause_summary="SimulatedDatabasePool saturated due to burst checkout volume.",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        # 1. Hypothesis
        hypo = Hypothesis(
            incident_id=incident.id,
            rank=1,
            title="DB Connection Pool Exhaustion",
            description="Pool capacity of 2 connections was insufficient for incoming transaction rate.",
            suspect_service="payment-service",
            proposed_cause="max_connections=2 bottleneck",
            status="VERIFIED",
        )
        session.add(hypo)

        # 2. Sandbox Run proof
        run = SandboxRun(
            incident_id=incident.id,
            hypothesis_id=hypo.id,
            service_name="payment-service",
            sandbox_type="PROCESS",
            port=9144,
            status="SUCCESS",
            exit_code=500,
            reproduction_verified=True,
            reproduction_signature="Timeout: DB connection pool exhausted",
        )
        session.add(run)

        # 3. Remediation with shadow validation metrics
        benchmarks = {
            "status": "VALIDATED",
            "pre_patch_errors": 8,
            "post_patch_errors": 0,
            "error_rate": 0.0,
            "latency_p95_ms": 42.5,
            "reproduced_issue_resolved": True,
        }
        rem = Remediation(
            incident_id=incident.id,
            hypothesis_id=hypo.id,
            patch_type="CONFIG",
            target_service="payment-service",
            diff_content="--- a/config.py\n+++ b/config.py\n-MAX_CONNS=2\n+MAX_CONNS=15",
            rollback_diff="--- a/config.py\n+++ b/config.py\n-MAX_CONNS=15\n+MAX_CONNS=2",
            policy_check_status="PASSED",
            validation_status="VALIDATED",
            validation_details_json=json.dumps(benchmarks),
            approval_status="APPROVED",
        )
        session.add(rem)

        # 4. Audit events
        audit1 = AuditEvent(incident_id=incident.id, event_type="INCIDENT_DETECTED", actor="DETECTOR")
        audit2 = AuditEvent(incident_id=incident.id, event_type="HYPOTHESES_GENERATED", actor="AGENT_RCA")
        audit3 = AuditEvent(incident_id=incident.id, event_type="REPRODUCTION_VERIFIED", actor="AGENT_VERIFICATION")
        audit4 = AuditEvent(incident_id=incident.id, event_type="REMEDIATION_APPLIED", actor="DEPLOYER_ORCHESTRATOR")
        session.add_all([audit1, audit2, audit3, audit4])
        await session.commit()
        await session.refresh(incident)

        generator = PostmortemGenerator()
        report = await generator.generate_postmortem(session, incident.id)

        assert report.incident_id == incident.id
        assert report.severity == "CRITICAL"
        assert report.mttd_seconds > 0.0
        assert "Post-Incident Review" in report.markdown
        assert "Executive Summary" in report.markdown
        assert "Root Cause Analysis (RCA)" in report.markdown
        assert "Empirical Sandbox Verification" in report.markdown
        assert "Shadow Validation Benchmarks" in report.markdown
        assert "Incident Timeline" in report.markdown
        assert "Preventative Action Items" in report.markdown
        assert len(report.timeline) >= 4
        assert len(report.action_items) == 3

        # Confirm saved in database
        await session.refresh(incident)
        assert incident.postmortem_markdown is not None
        assert "Executive Summary" in incident.postmortem_markdown


@pytest.mark.asyncio
async def test_git_pull_request_generator():
    """Validates generation of PR branch, diff, SRE checklist, and patch files."""
    async with async_session_factory() as session:
        incident = Incident(
            title="Payment Saturation Bug",
            severity="HIGH",
            status="RESOLVED",
            suspect_service="payment-service",
            root_cause_summary="Connection pool size was too small.",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        rem = Remediation(
            incident_id=incident.id,
            patch_type="CONFIG",
            target_service="payment-service",
            diff_content="--- a/pool.py\n+++ b/pool.py\n-SIZE=2\n+SIZE=15\n",
            rollback_diff="--- a/pool.py\n+++ b/pool.py\n-SIZE=15\n+SIZE=2\n",
            policy_check_status="PASSED",
            validation_status="VALIDATED",
            approval_status="APPROVED",
        )
        session.add(rem)
        await session.commit()
        await session.refresh(incident)

        pr_gen = PullRequestGenerator()
        dossier = await pr_gen.generate_pull_request(session, incident.id)

        assert dossier.incident_id == incident.id
        assert dossier.branch_name.startswith("traceheal/fix-payment-service-")
        assert "fix(payment-service)" in dossier.title
        assert "Automated Incident Remediation" in dossier.body_markdown
        assert "SRE Verification Checklist" in dossier.body_markdown
        assert "[x] Empirically reproduced in isolated shadow sandbox" in dossier.body_markdown
        assert dossier.patch_diff == rem.diff_content
        assert dossier.commit_hash is not None

        # Verify patch file on disk
        patch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "patches"))
        assert os.path.exists(patch_dir)
        patch_files = os.listdir(patch_dir)
        assert len(patch_files) >= 1

        # Verify saved in incident
        await session.refresh(incident)
        assert incident.pull_request_json is not None


@pytest.mark.asyncio
async def test_incident_closure_state_machine():
    """Validates that incident closure strictly requires RESOLVED state and records audit."""
    async with async_session_factory() as session:
        # 1. Reject closure from UNRESOLVED state (e.g. INVESTIGATING)
        unresolved = Incident(
            title="Unresolved Incident",
            severity="MEDIUM",
            status="INVESTIGATING",
        )
        session.add(unresolved)
        await session.commit()
        await session.refresh(unresolved)

        svc = PostmortemService()
        with pytest.raises(ValueError, match="must be 'RESOLVED' before closure"):
            await svc.close_incident(session, unresolved.id)

        # 2. Allow closure from RESOLVED state
        resolved = Incident(
            title="Resolved Incident",
            severity="HIGH",
            status="RESOLVED",
        )
        session.add(resolved)
        await session.commit()
        await session.refresh(resolved)

        closed = await svc.close_incident(
            db=session,
            incident_id=resolved.id,
            closed_by="SRE_DIRECTOR",
            notes="All verification tests passed. Postmortem published.",
        )
        assert closed.status == "CLOSED"
        assert closed.closed_at is not None

        # Verify audit trail
        stmt = select(AuditEvent).where(
            AuditEvent.incident_id == resolved.id,
            AuditEvent.event_type == "INCIDENT_CLOSED"
        )
        audits = (await session.execute(stmt)).scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_postmortem_rest_api_lifecycle(cluster):
    """Tests the complete Postmortem, PR, and Closure REST API lifecycle over HTTP transport."""
    async with async_session_factory() as session:
        incident = Incident(
            title="REST API Postmortem Incident",
            severity="HIGH",
            status="REMEDIATED",
            suspect_service="payment-service",
            root_cause_summary="Pool exhaustion fixed via remediation patch.",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        rem = Remediation(
            incident_id=incident.id,
            patch_type="CONFIG",
            target_service="payment-service",
            diff_content="--- a/cfg\n+++ b/cfg\n-MAX=2\n+MAX=15\n",
            rollback_diff="--- a/cfg\n+++ b/cfg\n-MAX=15\n+MAX=2\n",
            policy_check_status="PASSED",
            validation_status="VALIDATED",
            approval_status="APPROVED",
        )
        session.add(rem)
        await session.commit()
        await session.refresh(incident)
        inc_id = incident.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Validate recovery endpoint
        recov_resp = await client.post(
            f"/api/v1/postmortem/{inc_id}/validate-recovery?target_service_url=http://127.0.0.1:8082"
        )
        assert recov_resp.status_code == 200, recov_resp.text
        recov_data = recov_resp.json()
        assert recov_data["status"] == "RESOLVED"
        assert recov_data["recovery_confirmed"] is True

        # 2. Generate Postmortem endpoint
        pm_resp = await client.post(f"/api/v1/postmortem/{inc_id}/generate")
        assert pm_resp.status_code == 200, pm_resp.text
        pm_data = pm_resp.json()
        assert "Post-Incident Review" in pm_data["markdown"]
        assert len(pm_data["action_items"]) == 3

        # 3. Create PR endpoint
        pr_resp = await client.post(f"/api/v1/postmortem/{inc_id}/create-pr")
        assert pr_resp.status_code == 200, pr_resp.text
        pr_data = pr_resp.json()
        assert "traceheal/fix-" in pr_data["branch_name"]
        assert "SRE Verification Checklist" in pr_data["body_markdown"]

        # 4. Query incident postmortem details
        get_resp = await client.get(f"/api/v1/postmortem/{inc_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["postmortem_markdown"] is not None

        # 5. Close incident endpoint
        close_resp = await client.post(
            f"/api/v1/postmortem/{inc_id}/close",
            json={"closed_by": "VP_ENGINEERING", "notes": "Incident resolved, verified, and closed."},
        )
        assert close_resp.status_code == 200
        assert close_resp.json()["status"] == "CLOSED"
