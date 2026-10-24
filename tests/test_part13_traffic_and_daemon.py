"""Tests for Part 13: Continuous Background Traffic Controller and Anomaly Observation Daemon."""

import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.core.config import settings
from backend.app.db.session import init_db
from backend.app.incidents.daemon import AnomalyDetectorDaemon
from backend.app.llm.client import HybridLLMClient
from backend.app.main import app
from target_services.traffic_controller import TrafficController


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()


@pytest.mark.asyncio
async def test_traffic_controller_start_stop_lifecycle():
    """Validates that continuous traffic controller can be started, queried, and stopped cleanly."""
    tc = TrafficController(gateway_url="http://127.0.0.1:8080")
    assert tc.is_running is False
    status_init = tc.status()
    assert status_init["running"] is False
    assert status_init["total_sent"] == 0

    # Start at 5.0 RPS
    started = await tc.start(rate_rps=5.0)
    assert started["running"] is True
    assert started["rate_rps"] == 5.0
    assert tc.is_running is True

    # Let it run briefly
    await asyncio.sleep(0.5)

    status_running = tc.status()
    assert status_running["running"] is True
    assert status_running["uptime_seconds"] >= 0.0

    # Stop cleanly
    stopped = await tc.stop()
    assert stopped["running"] is False
    assert tc.is_running is False


@pytest.mark.asyncio
async def test_anomaly_detector_daemon_lifecycle():
    """Validates sliding-window anomaly detector daemon initialization and lifecycle."""
    daemon = AnomalyDetectorDaemon(check_interval_sec=0.2, error_threshold=0.15)
    assert daemon.is_running is False

    status = daemon.status()
    assert status["running"] is False
    assert status["error_threshold"] == 0.15

    await daemon.start()
    assert daemon.is_running is True

    await asyncio.sleep(0.5)

    running_status = daemon.status()
    assert running_status["running"] is True
    assert running_status["total_scans"] >= 1

    await daemon.stop()
    assert daemon.is_running is False


@pytest.mark.asyncio
async def test_traffic_and_daemon_api_endpoints():
    """Validates FastAPI endpoints for /api/v1/traffic."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Status query
        res = await ac.get("/api/v1/traffic/status")
        assert res.status_code == 200
        data = res.json()
        assert "traffic" in data
        assert "daemon" in data

        # 2. Start traffic via API
        start_res = await ac.post("/api/v1/traffic/start", json={"rate_rps": 2.0})
        assert start_res.status_code == 200
        assert start_res.json()["status"] == "STARTED"

        # 3. Stop traffic via API
        stop_res = await ac.post("/api/v1/traffic/stop")
        assert stop_res.status_code == 200
        assert stop_res.json()["status"] == "STOPPED"


@pytest.mark.asyncio
async def test_hybrid_llm_client_synthesis_and_fallback():
    """Validates HybridLLMClient generates accurate RCA and remediation patches with deterministic guarantee."""
    client = HybridLLMClient()

    # 1. RCA synthesis
    rca = await client.synthesize_rca_hypothesis(
        service_name="payment-service",
        error_message="DBPoolExhaustionError: connections limit 2 reached",
        attributes={"db.pool.exhausted": True, "db.pool.max_size": 2},
        causal_chain=["gateway-service", "order-service", "payment-service"],
        bottleneck={"service_name": "payment-service", "duration_ms": 1180.0},
    )
    assert "Pool" in rca["title"] or "Connection" in rca["title"]
    assert rca["confidence"] >= 0.8
    assert "reproduction_recipe" in rca

    # 2. Remediation diff synthesis
    patch = await client.synthesize_remediation_diff(
        service_name="payment-service",
        hypothesis_title=rca["title"],
        proposed_cause=rca["proposed_cause"],
        scenario="DB_POOL_EXHAUSTION",
    )
    assert patch["patch_type"] == "CONFIG"
    assert "DB_POOL_MAX_CONNECTIONS = 15" in patch["diff_content"]
    assert patch["rollback_diff"] != ""
