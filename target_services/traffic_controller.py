"""Continuous Background Traffic Controller for Live Autonomous Demos.

Generates realistic continuous synthetic transactions against the 6-tier microservices
cluster at configurable rates (e.g., 2 RPS, 5 RPS, 10 RPS, 25 RPS) with real-time telemetry.
"""

import asyncio
import random
import time
from typing import Any, Dict, Optional
import httpx

from backend.app.core.logging import logger


class TrafficController:
    """Manages continuous background synthetic customer traffic generation."""

    def __init__(self, gateway_url: str = "http://127.0.0.1:8080"):
        self.gateway_url = gateway_url
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._rate_rps: float = 2.0
        self._total_sent: int = 0
        self._success_count: int = 0
        self._error_count: int = 0
        self._last_status: Optional[int] = None
        self._last_latency_ms: float = 0.0
        self._start_time: Optional[float] = None
        self._items_catalog = ["item-101", "item-102", "item-103", "item-104", "item-105"]

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> Dict[str, Any]:
        elapsed = round(time.time() - self._start_time, 1) if self._start_time and self._running else 0.0
        return {
            "running": self._running,
            "rate_rps": self._rate_rps,
            "total_sent": self._total_sent,
            "success_count": self._success_count,
            "error_count": self._error_count,
            "error_rate": round(self._error_count / max(1, self._total_sent), 3),
            "last_status": self._last_status,
            "last_latency_ms": round(self._last_latency_ms, 2),
            "uptime_seconds": elapsed,
        }

    async def start(self, rate_rps: float = 2.0) -> Dict[str, Any]:
        """Starts continuous synthetic traffic at the given rate in RPS."""
        if self._running:
            self._rate_rps = max(0.5, min(50.0, rate_rps))
            return self.status()

        self._running = True
        self._rate_rps = max(0.5, min(50.0, rate_rps))
        self._start_time = time.time()
        self._total_sent = 0
        self._success_count = 0
        self._error_count = 0
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"[TRAFFIC] Continuous background traffic generator started at {self._rate_rps} RPS")
        return self.status()

    async def stop(self) -> Dict[str, Any]:
        """Stops continuous synthetic traffic."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[TRAFFIC] Continuous background traffic generator stopped")
        return self.status()

    async def _run_loop(self):
        """Asynchronous traffic loop sending requests at desired intervals."""
        while self._running:
            interval = 1.0 / max(0.1, self._rate_rps)
            t0 = time.time()
            try:
                await self._send_one()
            except Exception as e:
                logger.debug(f"[TRAFFIC] Background request dispatch error: {e}")

            elapsed = time.time() - t0
            sleep_time = max(0.01, interval - elapsed)
            try:
                await asyncio.sleep(sleep_time)
            except asyncio.CancelledError:
                break

    async def _send_one(self):
        """Dispatches a single synthetic checkout request through the gateway."""
        item_id = random.choice(self._items_catalog)
        qty = random.randint(1, 3)
        amount = round(random.uniform(19.99, 149.99), 2)
        order_seq = random.randint(1000, 99999)

        payload = {
            "order_id": f"ord_synth_{order_seq}",
            "items": [{"item_id": item_id, "quantity": qty}],
            "amount": amount,
            "currency": "USD",
        }

        t_start = time.time()
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(
                    f"{self.gateway_url}/api/v1/orders/checkout",
                    json=payload,
                )
                self._last_latency_ms = (time.time() - t_start) * 1000.0
                self._last_status = resp.status_code
                self._total_sent += 1
                if resp.status_code == 200:
                    self._success_count += 1
                else:
                    self._error_count += 1
        except Exception as exc:
            self._last_latency_ms = (time.time() - t_start) * 1000.0
            self._last_status = 504
            self._total_sent += 1
            self._error_count += 1


# Global singleton instance
traffic_controller = TrafficController()
