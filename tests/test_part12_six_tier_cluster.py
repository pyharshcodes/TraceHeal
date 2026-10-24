"""Test Suite for 6-Tier Enterprise Microservices Ecosystem.

Covers:
1. Full 6-tier cluster connectivity across ports 8080-8085
2. End-to-end checkout with auth verification and async notification delivery
3. Auth-Service Token Cascade Chaos injection and recovery
4. Notification-Service Message Queue Saturation Chaos injection and recovery
"""

import os
import sys
import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from target_services.cluster import ServiceCluster

GATEWAY_URL = "http://127.0.0.1:8080"
ORDER_URL = "http://127.0.0.1:8081"
PAYMENT_URL = "http://127.0.0.1:8082"
INVENTORY_URL = "http://127.0.0.1:8083"
AUTH_URL = "http://127.0.0.1:8084"
NOTIFICATION_URL = "http://127.0.0.1:8085"


@pytest_asyncio.fixture(scope="module", autouse=True)
async def cluster():
    """Starts the 6-tier microservice cluster for testing and tears it down afterward."""
    svc_cluster = ServiceCluster()
    await svc_cluster.start()
    ready = await svc_cluster.wait_until_ready(timeout=10.0)
    assert ready is True, "6-tier service cluster failed to reach ready state within 10s"
    yield svc_cluster
    await svc_cluster.stop()



@pytest.mark.asyncio
async def test_all_six_microservices_health():
    """Validates that all 6 microservices in the cluster respond healthy."""
    services = [
        ("gateway", GATEWAY_URL),
        ("order", ORDER_URL),
        ("payment", PAYMENT_URL),
        ("inventory", INVENTORY_URL),
        ("auth", AUTH_URL),
        ("notification", NOTIFICATION_URL),
    ]

    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in services:
            resp = await client.get(f"{url}/health")
            assert resp.status_code == 200, f"{name} failed health check"
            data = resp.json()
            assert data.get("status") == "UP"


@pytest.mark.asyncio
async def test_six_tier_e2e_checkout_propagation():
    """Validates full distributed order flow crossing all 6 services."""
    payload = {
        "order_id": "test_ord_6tier_suite",
        "items": [{"item_id": "item_laptop_01", "quantity": 1}],
        "amount": 1299.00,
        "currency": "USD",
    }

    async with httpx.AsyncClient(timeout=6.0) as client:
        resp = await client.post(f"{GATEWAY_URL}/api/v1/orders/checkout", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "CONFIRMED"
        assert "inventory" in data
        assert data["inventory"]["status"] == "RESERVED"
        assert "payment" in data
        assert data["payment"]["status"] == "CHARGED"
        assert "notification" in data
        assert data["notification"]["status"] in ("DELIVERED", "QUEUED")


@pytest.mark.asyncio
async def test_auth_service_chaos_and_recovery():
    """Tests injecting token validation chaos into auth-service and verifying gateway protection."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Inject auth error
        inject_res = await client.post(f"{AUTH_URL}/chaos/inject", json={"force_error": True, "expire_all": True})
        assert inject_res.status_code == 200

        # 2. Checkout should fail at gateway with 401 Unauthorized
        fail_res = await client.post(
            f"{GATEWAY_URL}/api/v1/orders/checkout",
            json={"items": [{"item_id": "item_watch", "quantity": 1}], "amount": 199.00},
        )
        assert fail_res.status_code in (401, 502)

        # 3. Reset chaos
        reset_res = await client.post(f"{AUTH_URL}/chaos/reset")
        assert reset_res.status_code == 200

        # 4. Recovery: checkout succeeds again
        recovery_res = await client.post(
            f"{GATEWAY_URL}/api/v1/orders/checkout",
            json={"items": [{"item_id": "item_watch", "quantity": 1}], "amount": 199.00},
        )
        assert recovery_res.status_code == 200


@pytest.mark.asyncio
async def test_notification_service_queue_overflow():
    """Tests async message queue saturation chaos on notification-service."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Inject queue overflow
        inject_res = await client.post(f"{NOTIFICATION_URL}/chaos/inject", json={"queue_overflow": True})
        assert inject_res.status_code == 200

        # 2. Direct notification dispatch returns 503 DLQ overflow
        notif_res = await client.post(
            f"{NOTIFICATION_URL}/notifications/send",
            json={"order_id": "test_fail_queue", "recipient": "test@domain.com", "channel": "EMAIL"},
        )
        assert notif_res.status_code == 503
        assert "DeadLetterQueueOverflowError" in notif_res.text

        # 3. Reset chaos
        reset_res = await client.post(f"{NOTIFICATION_URL}/chaos/reset")
        assert reset_res.status_code == 200
