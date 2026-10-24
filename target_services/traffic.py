"""Traffic generator for generating baseline and burst loads against the API Gateway."""

import asyncio
from typing import Any, Dict, List
import httpx


class TrafficGenerator:
    """Generates synthetic client traffic against the API Gateway."""

    def __init__(self, gateway_url: str = "http://127.0.0.1:8080"):
        self.gateway_url = gateway_url

    async def send_single_checkout(
        self,
        order_id: str = "ord_test_01",
        amount: float = 49.99,
        items: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Sends a single order checkout request."""
        if items is None:
            items = [{"item_id": "item-101", "quantity": 1}]

        payload = {
            "order_id": order_id,
            "items": items,
            "amount": amount,
            "currency": "USD",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{self.gateway_url}/api/v1/orders/checkout", json=payload)
            return {
                "status_code": resp.status_code,
                "data": resp.json() if resp.status_code in (200, 500, 502) else resp.text,
            }

    async def send_burst_checkouts(
        self,
        concurrency: int = 8,
        total_requests: int = 10,
    ) -> List[Dict[str, Any]]:
        """Sends burst concurrent checkout requests to induce resource contention."""
        sem = asyncio.Semaphore(concurrency)
        async with httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        ) as client:
            async def _worker(i: int):
                async with sem:
                    payload = {
                        "order_id": f"burst_ord_{i}",
                        "items": [{"item_id": "item-101", "quantity": 1}],
                        "amount": 10.0 + i,
                        "currency": "USD",
                    }
                    try:
                        resp = await client.post(f"{self.gateway_url}/api/v1/orders/checkout", json=payload)
                        return {
                            "status_code": resp.status_code,
                            "data": resp.json() if resp.status_code in (200, 500, 502) else resp.text,
                        }
                    except Exception as exc:
                        return {"status_code": 504, "data": str(exc)}

            tasks = [_worker(i) for i in range(total_requests)]
            return await asyncio.gather(*tasks, return_exceptions=False)
