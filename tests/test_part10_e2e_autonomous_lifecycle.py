"""Tests for Part 10: End-to-End Autonomous Lifecycle, Orchestration & Production CLI."""

import os
import pytest
import pytest_asyncio
from click.testing import CliRunner
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app.db.models import Incident, Remediation
from backend.app.db.session import async_session_factory, init_db
from backend.app.main import app
from backend.app.orchestrator.lifecycle import AutonomousLifecycleOrchestrator
from cli.main import cli


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Initializes the database schema before each test."""
    await init_db()


@pytest.mark.asyncio
async def test_orchestrator_full_cycle_execution():
    """Validates the full 7-phase autonomous closed-loop self-healing sequence."""
    orchestrator = AutonomousLifecycleOrchestrator()

    async with async_session_factory() as db:
        manifest = await orchestrator.run_full_autonomous_cycle(
            db=db,
            scenario="DB_POOL_EXHAUSTION",
            target_service="payment-service",
            trace_count=2,
            live_cluster=False,
        )

        # Assert status and lifecycle sequence
        assert manifest["status"] == "AUTONOMOUS_CYCLE_COMPLETE"
        assert manifest["final_status"] == "CLOSED"
        assert manifest["suspect_service"] == "payment-service"
        assert manifest["lifecycle_progression"] == [
            "DETECTED",
            "INVESTIGATING",
            "REPRODUCING",
            "VERIFIED",
            "REMEDIATED",
            "RESOLVED",
            "CLOSED",
        ]

        # Verify PR and patch generation
        assert manifest["pull_request"]["branch_name"].startswith("traceheal/")
        patch_file = manifest["pull_request"]["patch_file"]
        if not os.path.exists(patch_file):
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            alt_path = os.path.join(repo_root, patch_file)
            if os.path.exists(alt_path):
                patch_file = alt_path
        assert os.path.exists(patch_file), f"Patch file {patch_file} does not exist on disk"
        with open(patch_file, "r") as f:
            patch_text = f.read()
        assert "--- a/" in patch_text and "+++ b/" in patch_text
        assert "pool_size" in patch_text or "connection" in patch_text or "DB_POOL" in patch_text

        # Verify database state consistency
        inc_res = await db.execute(select(Incident).where(Incident.id == manifest["incident_id"]))
        incident = inc_res.scalar_one_or_none()
        assert incident is not None
        assert incident.status == "CLOSED"
        assert incident.resolved_at is not None

        assert incident.postmortem_markdown is not None
        assert "POST-INCIDENT REVIEW" in incident.postmortem_markdown.upper()


@pytest.mark.asyncio
async def test_orchestrator_api_endpoint():
    """Validates POST /api/v1/orchestrator/run-cycle HTTP API endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "scenario": "PAYMENT_TIMEOUT",
            "target_service": "payment-service",
            "trace_count": 2,
            "live_cluster": False,
        }
        resp = await client.post("/api/v1/orchestrator/run-cycle", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "AUTONOMOUS_CYCLE_COMPLETE"
        assert data["final_status"] == "CLOSED"
        assert data["lifecycle_progression"] == [
            "DETECTED",
            "INVESTIGATING",
            "REPRODUCING",
            "VERIFIED",
            "REMEDIATED",
            "RESOLVED",
            "CLOSED",
        ]
        assert "incident_id" in data
        assert "pull_request" in data
        assert "remediation" in data
        assert data["total_execution_seconds"] > 0


def test_cli_version_and_commands():
    """Validates Click CLI version, cluster status, and incident listing commands."""
    runner = CliRunner()

    # Test version command
    v_res = runner.invoke(cli, ["version"])
    assert v_res.exit_code == 0
    assert "TraceHeal Core Engine" in v_res.output
    assert "Autonomous Incident Investigation" in v_res.output

    # Test cluster status command
    c_res = runner.invoke(cli, ["cluster", "status"])
    assert c_res.exit_code == 0
    assert "gateway-service" in c_res.output
    assert "payment-service" in c_res.output

    # Test incident list command
    i_res = runner.invoke(cli, ["incident", "list"])
    assert i_res.exit_code == 0
    assert "ID" in i_res.output or "No incidents recorded" in i_res.output


def test_cli_auto_heal_and_postmortem():
    """Validates Click CLI 'auto-heal' end-to-end execution and 'postmortem' report viewer."""
    runner = CliRunner()

    # Execute autonomous healing cycle via CLI
    heal_res = runner.invoke(cli, ["auto-heal", "--trace-count", "2", "--scenario", "LATENCY_SPIKE"])
    assert heal_res.exit_code == 0
    assert "AUTONOMOUS CLOSED-LOOP SELF-HEALING ENGINE" in heal_res.output
    assert "[SUCCESS] AUTONOMOUS SELF-HEALING CYCLE COMPLETED!" in heal_res.output
    assert "Final State        : CLOSED" in heal_res.output
    assert "Git PR Branch      : traceheal/" in heal_res.output

    # Parse incident ID from output to test postmortem command
    output_lines = heal_res.output.splitlines()
    incident_id = None
    for line in output_lines:
        if "Incident ID" in line:
            incident_id = line.split(":")[-1].strip()
            break

    assert incident_id is not None, "Failed to capture incident ID from CLI output"

    # View postmortem report via CLI
    pm_res = runner.invoke(cli, ["postmortem", incident_id])
    assert pm_res.exit_code == 0
    assert "POST-INCIDENT REVIEW" in pm_res.output.upper()
    assert incident_id in pm_res.output
