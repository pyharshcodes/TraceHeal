"""Tests for Part 6: Safe Patch Generation, Policy Verification & Shadow Remediation."""

import json
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.agents.remediation_agent import RemediationAgent
from backend.app.db.models import AuditEvent, Hypothesis, Incident, Remediation
from backend.app.db.session import async_session_factory, init_db
from backend.app.main import app
from backend.app.remediation.deployer import RemediationDeployer
from backend.app.remediation.policy_engine import PolicyEngine
from target_services.cluster import ServiceCluster


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()


@pytest.mark.asyncio
async def test_remediation_policy_engine_allowlist_and_denylist():
    """Validates security guardrails, allowlists, boundaries, and denylists."""
    # 1. Valid proposal passes
    valid_res = PolicyEngine.evaluate(
        target_service="payment-service",
        diff_content="--- a/config.py\n+++ b/config.py\n-MAX_CONNS=2\n+MAX_CONNS=15",
        patch_type="CONFIG",
        config_parameters={"max_connections": 15, "acquire_timeout_sec": 0.5},
        rollback_diff="--- a/config.py\n+++ b/config.py\n-MAX_CONNS=15\n+MAX_CONNS=2",
    )
    assert valid_res.status == "PASSED"
    assert len(valid_res.violations) == 0
    assert "RULE_SERVICE_ALLOWLIST" in valid_res.passed_rules
    assert "RULE_NO_DANGEROUS_COMMANDS" in valid_res.passed_rules
    assert "RULE_PARAMETER_BOUNDARIES" in valid_res.passed_rules

    # 2. Unknown service is rejected
    invalid_svc = PolicyEngine.evaluate(
        target_service="untrusted-external-daemon",
        diff_content="--- a/cfg\n+++ b/cfg\n+PORT=1234",
        rollback_diff="--- a/cfg\n+++ b/cfg\n-PORT=1234",
    )
    assert invalid_svc.status == "REJECTED"
    assert any("allowed services" in v.lower() for v in invalid_svc.violations)

    # 3. Dangerous command pattern is rejected
    malicious_res = PolicyEngine.evaluate(
        target_service="payment-service",
        diff_content="import os\nos.system('rm -rf /')\n",
        rollback_diff="echo 'revert'",
    )
    assert malicious_res.status == "REJECTED"
    assert any("dangerous patterns" in v.lower() for v in malicious_res.violations)

    # 4. Out-of-bounds parameter is rejected
    oob_res = PolicyEngine.evaluate(
        target_service="payment-service",
        diff_content="--- a/cfg\n+++ b/cfg\n+MAX=500",
        config_parameters={"max_connections": 500},  # Upper bound is 100
        rollback_diff="--- a/cfg\n+++ b/cfg\n-MAX=500",
    )
    assert oob_res.status == "REJECTED"
    assert any("outside safe boundary" in v.lower() for v in oob_res.violations)

    # 5. Missing rollback diff is rejected
    no_rollback = PolicyEngine.evaluate(
        target_service="payment-service",
        diff_content="--- a/cfg\n+++ b/cfg\n+MAX=15",
        rollback_diff="",
    )
    assert no_rollback.status == "REJECTED"
    assert any("rollback diff" in v.lower() for v in no_rollback.violations)


@pytest.mark.asyncio
async def test_remediation_agent_synthesis_and_diff_generation():
    """Validates autonomous synthesis of policy-checked remediation proposals."""
    async with async_session_factory() as session:
        # Create incident in VERIFIED state
        incident = Incident(
            title="Payment Database Pool Exhaustion",
            severity="HIGH",
            status="VERIFIED",
            suspect_service="payment-service",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        # Create verified hypothesis with reproduction recipe
        recipe = {
            "scenario": "DB_POOL_EXHAUSTION",
            "endpoint": "/payments/charge",
            "concurrency": 8,
            "parameters": {"max_connections": 2, "acquire_timeout_sec": 0.1, "hold_duration_sec": 0.25},
            "expected_error_signature": "DBPoolExhaustionError",
        }
        hypothesis = Hypothesis(
            incident_id=incident.id,
            rank=1,
            title="Database Connection Pool Exhaustion",
            description="Connection pool size 2 exhausted under burst traffic.",
            suspect_service="payment-service",
            proposed_cause="SimulatedDatabasePool max_connections=2 is too small.",
            status="VERIFIED",
            reproduction_recipe_json=json.dumps(recipe),
        )
        session.add(hypothesis)
        await session.commit()
        await session.refresh(hypothesis)

        agent = RemediationAgent()
        rem = await agent.propose_remediation(session, incident.id, hypothesis.id)

        assert rem.incident_id == incident.id
        assert rem.hypothesis_id == hypothesis.id
        assert rem.target_service == "payment-service"
        assert rem.patch_type == "CONFIG"
        assert rem.policy_check_status == "PASSED"
        assert rem.validation_status == "PENDING"
        assert rem.approval_status == "PENDING_APPROVAL"
        assert "DB_POOL_MAX_CONNECTIONS = 15" in rem.diff_content
        assert rem.rollback_diff is not None

        # Verify audit trail
        stmt = select(AuditEvent).where(
            AuditEvent.incident_id == incident.id,
            AuditEvent.event_type == "REMEDIATION_PROPOSED"
        )
        res = await session.execute(stmt)
        audits = res.scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_shadow_sandbox_validation_proves_fix():
    """Empirically proves that applying the proposed patch inside an isolated sandbox eliminates errors."""
    async with async_session_factory() as session:
        incident = Incident(
            title="Payment Pool Failure for Shadow Test",
            severity="CRITICAL",
            status="VERIFIED",
            suspect_service="payment-service",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        recipe = {
            "scenario": "DB_POOL_EXHAUSTION",
            "endpoint": "/payments/charge",
            "concurrency": 6,
            "parameters": {"max_connections": 2, "acquire_timeout_sec": 0.1, "hold_duration_sec": 0.2},
            "expected_error_signature": "DBPoolExhaustionError",
        }
        hypothesis = Hypothesis(
            incident_id=incident.id,
            rank=1,
            title="Pool Contention",
            description="Pool size 2 causes timeouts.",
            suspect_service="payment-service",
            proposed_cause="max_connections=2 bottleneck",
            status="VERIFIED",
            reproduction_recipe_json=json.dumps(recipe),
        )
        session.add(hypothesis)
        await session.commit()
        await session.refresh(hypothesis)

        agent = RemediationAgent()
        rem = await agent.propose_remediation(session, incident.id, hypothesis.id)

        # Execute shadow validation
        deployer = RemediationDeployer()
        val_res = await deployer.execute_shadow_validation(session, rem.id)

        assert val_res.status == "VALIDATED"
        assert val_res.reproduced_issue_resolved is True
        assert val_res.error_rate == 0.0
        assert val_res.post_patch_errors == 0

        # Query updated remediation record
        await session.refresh(rem)
        assert rem.validation_status == "VALIDATED"
        assert rem.validation_details_json is not None

        # Verify audit event
        stmt = select(AuditEvent).where(
            AuditEvent.incident_id == incident.id,
            AuditEvent.event_type == "REMEDIATION_SHADOW_VALIDATED"
        )
        res = await session.execute(stmt)
        audits = res.scalars().all()
        assert len(audits) >= 1


@pytest.mark.asyncio
async def test_approval_gate_and_state_machine_enforcement():
    """Validates approval preconditions and live application with state machine transitions."""
    async with async_session_factory() as session:
        incident = Incident(
            title="State Machine Enforcement Incident",
            severity="HIGH",
            status="VERIFIED",
            suspect_service="payment-service",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        rem = Remediation(
            incident_id=incident.id,
            patch_type="CONFIG",
            target_service="payment-service",
            diff_content="--- a/cfg\n+++ b/cfg\n+MAX=15",
            rollback_diff="--- a/cfg\n+++ b/cfg\n-MAX=15",
            policy_check_status="PASSED",
            validation_status="PENDING",
            approval_status="PENDING_APPROVAL",
        )
        session.add(rem)
        await session.commit()
        await session.refresh(rem)

        deployer = RemediationDeployer()

        # 1. Approval must fail if validation_status is not VALIDATED
        with pytest.raises(ValueError, match="shadow validation must be 'VALIDATED'"):
            await deployer.approve_remediation(session, rem.id, decision="APPROVE")

        # Set validation to VALIDATED
        rem.validation_status = "VALIDATED"
        await session.commit()

        # 2. Cannot apply before approval
        with pytest.raises(ValueError, match="must be 'APPROVED'"):
            await deployer.apply_remediation(session, rem.id)

        # 3. Approve remediation
        approved = await deployer.approve_remediation(
            session,
            rem.id,
            approver="SRE_SENIOR",
            decision="APPROVE",
            notes="Shadow validation empirically confirmed 0% error rate.",
        )
        assert approved.approval_status == "APPROVED"

        # 4. Spin up cluster to test live deployment against payment-service
        cluster = ServiceCluster()
        await cluster.start()
        try:
            apply_res = await deployer.apply_remediation(
                session,
                rem.id,
                target_base_url="http://127.0.0.1:8082",
            )
            assert apply_res["status"] == "APPLIED"
            assert apply_res["incident_status"] == "REMEDIATED"

            # Check that incident state was transitioned to REMEDIATED
            await session.refresh(incident)
            assert incident.status == "REMEDIATED"
            await session.refresh(rem)
            assert rem.applied_at is not None

            # Test Rollback
            rollback_res = await deployer.rollback_remediation(
                session,
                rem.id,
                target_base_url="http://127.0.0.1:8082",
            )
            assert rollback_res["status"] == "ROLLED_BACK"

        finally:
            await cluster.stop()


@pytest.mark.asyncio
async def test_remediations_rest_api_lifecycle():
    """Tests the complete Remediation REST API flow over HTTP transport."""
    async with async_session_factory() as session:
        incident = Incident(
            title="REST API Remediation Test",
            severity="HIGH",
            status="VERIFIED",
            suspect_service="payment-service",
        )
        session.add(incident)
        await session.commit()
        await session.refresh(incident)

        recipe = {
            "scenario": "DB_POOL_EXHAUSTION",
            "endpoint": "/payments/charge",
            "concurrency": 6,
            "parameters": {"max_connections": 2, "acquire_timeout_sec": 0.1, "hold_duration_sec": 0.2},
            "expected_error_signature": "DBPoolExhaustionError",
        }
        hypo = Hypothesis(
            incident_id=incident.id,
            rank=1,
            title="Pool Starvation",
            description="Testing via REST",
            suspect_service="payment-service",
            proposed_cause="SimulatedDatabasePool max_connections=2",
            status="VERIFIED",
            reproduction_recipe_json=json.dumps(recipe),
        )
        session.add(hypo)
        await session.commit()
        await session.refresh(hypo)

        inc_id = incident.id
        hypo_id = hypo.id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Propose remediation
        resp = await client.post(f"/api/v1/remediations/propose/{inc_id}?hypothesis_id={hypo_id}")
        assert resp.status_code == 200, resp.text
        rem_data = resp.json()
        rem_id = rem_data["id"]
        assert rem_data["policy_check_status"] == "PASSED"
        assert rem_data["approval_status"] == "PENDING_APPROVAL"

        # 2. Policy check endpoint
        pol_resp = await client.post(f"/api/v1/remediations/{rem_id}/policy-check")
        assert pol_resp.status_code == 200
        assert pol_resp.json()["status"] == "PASSED"

        # 3. Shadow validation endpoint
        val_resp = await client.post(f"/api/v1/remediations/{rem_id}/shadow-validate")
        assert val_resp.status_code == 200, val_resp.text
        val_data = val_resp.json()
        assert val_data["status"] == "VALIDATED"
        assert val_data["reproduced_issue_resolved"] is True

        # 4. Approval endpoint
        appr_resp = await client.post(
            f"/api/v1/remediations/{rem_id}/approve",
            json={"decision": "APPROVE", "approver": "DEV_ONCALL", "notes": "Approved after shadow validation."},
        )
        assert appr_resp.status_code == 200
        assert appr_resp.json()["approval_status"] == "APPROVED"

        # 5. Query remediation details
        get_resp = await client.get(f"/api/v1/remediations/{rem_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["validation_status"] == "VALIDATED"

        # 6. List remediations for incident
        list_resp = await client.get(f"/api/v1/remediations/incident/{inc_id}")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1
