"""Test suite for Part 2: Target Microservice Ecosystem and Chaos Injection Engine.

Tests:
1. Cluster startup, readiness, and health checks across 4 services.
2. End-to-end checkout flow with full W3C distributed trace context propagation.
3. Chaos injection: PostgreSQL connection pool exhaustion under concurrent burst load.
4. Distributed error propagation and error span capture with root-cause signatures.
5. Chaos reset and full cluster recovery back to baseline performance.
"""

import asyncio
import os
import sys
import pytest
import pytest_asyncio
import httpx

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from target_services.cluster import ServiceCluster
from target_services.chaos import ChaosEngine, ChaosScenario
from target_services.traffic import TrafficGenerator
from target_services.tracer import collector, parse_traceparent


@pytest_asyncio.fixture(scope="module")
async def cluster():
    """Starts the 4-tier microservice cluster for testing and tears it down afterward."""
    svc_cluster = ServiceCluster()
    await svc_cluster.start()
    ready = await svc_cluster.wait_until_ready(timeout=10.0)
    assert ready is True, "Service cluster failed to reach ready state within 10s"
    yield svc_cluster
    await svc_cluster.stop()


@pytest.mark.asyncio
async def test_cluster_health_endpoints(cluster):
    """Verifies that all 4 microservices respond with healthy status."""
    chaos = ChaosEngine()
    statuses = await chaos.get_cluster_status()

    assert "gateway-service" in statuses
    assert "order-service" in statuses
    assert "payment-service" in statuses
    assert "inventory-service" in statuses

    for service_name, data in statuses.items():
        assert data.get("status") == "UP", f"{service_name} is not UP: {data}"


@pytest.mark.asyncio
async def test_e2e_checkout_and_w3c_trace_propagation(cluster):
    """Tests a successful end-to-end checkout flow across the 4 services

    and verifies that spans across all services share the exact same W3C trace_id.
    """
    collector.clear()
    traffic = TrafficGenerator()

    result = await traffic.send_single_checkout(order_id="e2e_test_order_01", amount=75.00)
    assert result["status_code"] == 200, f"Checkout failed: {result}"
    assert result["data"]["status"] == "CONFIRMED"
    assert "payment" in result["data"]
    assert "inventory" in result["data"]

    # Small delay to ensure all async finish hooks recorded spans
    await asyncio.sleep(0.1)

    spans = collector.get_spans()
    assert len(spans) >= 4, f"Expected at least 4 spans, got {len(spans)}"

    # Extract distinct trace IDs involved
    trace_ids = {s["trace_id"] for s in spans}
    assert len(trace_ids) == 1, f"All spans must belong to the same trace, found: {trace_ids}"

    # Verify each service recorded spans
    services_in_trace = {s["service_name"] for s in spans}
    assert "gateway-service" in services_in_trace
    assert "order-service" in services_in_trace
    assert "payment-service" in services_in_trace
    assert "inventory-service" in services_in_trace

    # Verify span statuses are all OK
    for s in spans:
        assert s["status_code"] == "OK", f"Span {s['operation_name']} failed: {s}"
        assert s["duration_ms"] > 0


@pytest.mark.asyncio
async def test_chaos_db_pool_exhaustion_under_burst_load(cluster):
    """Tests injecting DB connection pool exhaustion in payment-service and sending

    concurrent burst load. Verifies that requests fail with DBPoolExhaustionError
    and that error spans are recorded.
    """
    collector.clear()
    chaos = ChaosEngine()
    traffic = TrafficGenerator()

    # 1. Inject Chaos: Pool size = 2, hold time = 0.35s, acquire timeout = 0.2s
    inject_resp = await chaos.inject(
        ChaosScenario.DB_POOL_EXHAUSTION,
        target_service="payment-service",
        max_connections=2,
        acquire_timeout_sec=0.1,
        hold_duration_sec=0.25,
    )
    assert inject_resp["status"] == "CHAOS_INJECTED"
    assert inject_resp["pool"]["max_connections"] == 2

    # 2. Fire 8 burst requests concurrently
    burst_results = await traffic.send_burst_checkouts(concurrency=8, total_requests=8)

    # Some requests succeed, but contention must cause failures
    status_codes = [r["status_code"] for r in burst_results]
    failures = [r for r in burst_results if r["status_code"] in (500, 502)]

    assert len(failures) > 0, f"Expected pool exhaustion failures under burst load, but got: {status_codes}"

    # Verify failure detail contains pool exhaustion signature
    first_failure = failures[0]
    failure_text = str(first_failure["data"])
    assert "DBPoolExhaustionError" in failure_text or "Timeout acquiring connection from database pool" in failure_text, (
        f"Failure did not contain expected pool exhaustion signature: {failure_text}"
    )

    await asyncio.sleep(0.1)

    # 3. Verify error spans were captured in collector
    spans = collector.get_spans()
    error_spans = [s for s in spans if s["status_code"] == "ERROR"]
    assert len(error_spans) > 0, "No ERROR spans were recorded by tracer during pool exhaustion"

    payment_error_spans = [s for s in error_spans if s["service_name"] == "payment-service"]
    assert len(payment_error_spans) > 0, "Payment service failed to record error span"
    assert payment_error_spans[0]["http_status_code"] == 500


@pytest.mark.asyncio
async def test_chaos_reset_and_full_recovery(cluster):
    """Verifies resetting chaos restores 100% healthy operation under normal load."""
    collector.clear()
    chaos = ChaosEngine()
    traffic = TrafficGenerator()

    # Reset all chaos
    reset_resp = await chaos.reset_all()
    assert "payment-service" in reset_resp
    assert reset_resp["payment-service"]["status"] == "CHAOS_RESET"

    # Send a checkout request
    result = await traffic.send_single_checkout(order_id="recovered_ord_01", amount=19.99)
    assert result["status_code"] == 200, f"Checkout failed after chaos reset: {result}"
    assert result["data"]["status"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_inventory_outage_chaos_propagation(cluster):
    """Tests injecting an inventory outage and verifies gateway receives 502 Bad Gateway."""
    chaos = ChaosEngine()
    traffic = TrafficGenerator()

    # Inject inventory outage
    await chaos.inject(ChaosScenario.INVENTORY_OUTAGE, target_service="inventory-service")

    # Send checkout
    result = await traffic.send_single_checkout(order_id="inv_outage_01", amount=30.0)
    assert result["status_code"] in (500, 502)

    # Reset
    await chaos.reset_all()
    recovery = await traffic.send_single_checkout(order_id="inv_recovered_01", amount=30.0)
    assert recovery["status_code"] == 200
