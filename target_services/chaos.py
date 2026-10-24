"""Chaos Engine for programmatic failure injection across target microservices."""

from enum import Enum
from typing import Any, Dict, Optional
import httpx


class ChaosScenario(str, Enum):
    DB_POOL_EXHAUSTION = "DB_POOL_EXHAUSTION"
    LATENCY_SPIKE = "LATENCY_SPIKE"
    DEADLOCK = "DEADLOCK"
    INVENTORY_OUTAGE = "INVENTORY_OUTAGE"
    TOKEN_CASCADE = "TOKEN_CASCADE"
    QUEUE_SATURATION = "QUEUE_SATURATION"


class ChaosEngine:
    """Controls and coordinates chaos injection across the 6-tier microservice cluster."""

    def __init__(
        self,
        gateway_url: str = "http://127.0.0.1:8080",
        order_url: str = "http://127.0.0.1:8081",
        payment_url: str = "http://127.0.0.1:8082",
        inventory_url: str = "http://127.0.0.1:8083",
        auth_url: str = "http://127.0.0.1:8084",
        notification_url: str = "http://127.0.0.1:8085",
    ):
        self.urls = {
            "gateway-service": gateway_url,
            "order-service": order_url,
            "payment-service": payment_url,
            "inventory-service": inventory_url,
            "auth-service": auth_url,
            "notification-service": notification_url,
        }

    async def inject(
        self,
        scenario: ChaosScenario,
        target_service: str = "payment-service",
        **params,
    ) -> Dict[str, Any]:
        """Injects a specified chaos scenario into a target microservice."""
        if target_service not in self.urls:
            raise ValueError(f"Unknown service '{target_service}'. Known: {list(self.urls.keys())}")

        service_url = self.urls[target_service]

        async with httpx.AsyncClient(timeout=5.0) as client:
            if scenario == ChaosScenario.DB_POOL_EXHAUSTION:
                payload = {
                    "scenario": "DB_POOL_EXHAUSTION",
                    "max_connections": params.get("max_connections", 2),
                    "acquire_timeout_sec": params.get("acquire_timeout_sec", 0.25),
                    "hold_duration_sec": params.get("hold_duration_sec", 0.4),
                }
                resp = await client.post(f"{service_url}/chaos/inject", json=payload)
                return resp.json()

            elif scenario == ChaosScenario.LATENCY_SPIKE:
                latency = params.get("latency_sec", 2.0)
                if target_service == "payment-service":
                    payload = {"extra_latency_sec": latency}
                else:
                    payload = {"latency_sec": latency}
                resp = await client.post(f"{service_url}/chaos/inject", json=payload)
                return resp.json()

            elif scenario == ChaosScenario.DEADLOCK:
                payload = {"force_deadlock": True}
                resp = await client.post(f"{service_url}/chaos/inject", json=payload)
                return resp.json()

            elif scenario == ChaosScenario.INVENTORY_OUTAGE:
                payload = {"force_error": True}
                resp = await client.post(f"{self.urls['inventory-service']}/chaos/inject", json=payload)
                return resp.json()

            elif scenario == ChaosScenario.TOKEN_CASCADE:
                payload = {"force_error": True, "expire_all": True}
                resp = await client.post(f"{self.urls['auth-service']}/chaos/inject", json=payload)
                return resp.json()

            elif scenario == ChaosScenario.QUEUE_SATURATION:
                payload = {"force_error": True, "queue_overflow": True}
                resp = await client.post(f"{self.urls['notification-service']}/chaos/inject", json=payload)
                return resp.json()

            else:
                raise ValueError(f"Unsupported scenario: {scenario}")

    async def reset_all(self) -> Dict[str, Any]:
        """Resets chaos configuration on all services back to healthy defaults."""
        results = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for service_name, url in self.urls.items():
                try:
                    resp = await client.post(f"{url}/chaos/reset")
                    results[service_name] = resp.json()
                except Exception as exc:
                    results[service_name] = {"error": str(exc)}
        return results

    async def get_cluster_status(self) -> Dict[str, Any]:
        """Queries health and chaos status across all services."""
        statuses = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for service_name, url in self.urls.items():
                try:
                    resp = await client.get(f"{url}/health")
                    statuses[service_name] = resp.json()
                except Exception as exc:
                    statuses[service_name] = {"status": "DOWN", "error": str(exc)}
        return statuses
