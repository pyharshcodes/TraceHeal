"""ServiceCluster orchestrator for starting, monitoring, and stopping

the 4-tier microservice cluster (Gateway, Order, Payment, Inventory).
"""

import asyncio
import sys
import time
from typing import Dict, List, Optional
import httpx
import uvicorn

from target_services.gateway_service import app as gateway_app
from target_services.order_service import app as order_app
from target_services.payment_service import app as payment_app
from target_services.inventory_service import app as inventory_app
from target_services.auth_service import app as auth_app
from target_services.notification_service import app as notification_app


class ServiceCluster:
    """Manages the lifecycle of the 6-tier microservice cluster in asyncio tasks."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        gateway_port: int = 8080,
        order_port: int = 8081,
        payment_port: int = 8082,
        inventory_port: int = 8083,
        auth_port: int = 8084,
        notification_port: int = 8085,
    ):
        self.host = host
        self.ports = {
            "gateway-service": gateway_port,
            "order-service": order_port,
            "payment-service": payment_port,
            "inventory-service": inventory_port,
            "auth-service": auth_port,
            "notification-service": notification_port,
        }
        self.apps = {
            "gateway-service": gateway_app,
            "order-service": order_app,
            "payment-service": payment_app,
            "inventory-service": inventory_app,
            "auth-service": auth_app,
            "notification-service": notification_app,
        }
        self.servers: Dict[str, uvicorn.Server] = {}
        self.tasks: List[asyncio.Task] = []
        self._is_running = False

    async def start(self):
        """Starts all 4 microservices asynchronously, or binds to existing cluster."""
        if self._is_running:
            return

        # Check if cluster is already active on host ports
        if await self.wait_until_ready(timeout=0.8):
            self._is_running = True
            self._external = True
            return

        for name, app in self.apps.items():
            port = self.ports[name]
            config = uvicorn.Config(
                app=app,
                host=self.host,
                port=port,
                log_level="warning",
                access_log=False,
            )
            server = uvicorn.Server(config=config)
            self.servers[name] = server
            task = asyncio.create_task(server.serve())
            self.tasks.append(task)

        self._is_running = True

    async def wait_until_ready(self, timeout: float = 10.0) -> bool:
        """Polls health check on all services until ready or timeout."""
        start_time = time.time()
        async with httpx.AsyncClient(timeout=1.0) as client:
            while time.time() - start_time < timeout:
                ready_count = 0
                for name, port in self.ports.items():
                    url = f"http://{self.host}:{port}/health"
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            ready_count += 1
                    except Exception:
                        pass
                if ready_count == len(self.ports):
                    return True
                await asyncio.sleep(0.2)
        return False

    async def stop(self):
        """Gracefully terminates all services."""
        if not self._is_running:
            return

        if getattr(self, "_external", False):
            self._is_running = False
            return

        for server in self.servers.values():
            server.should_exit = True

        for task in self.tasks:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        self.servers.clear()
        self.tasks.clear()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running


async def run_cluster_cli():
    cluster = ServiceCluster()
    print("[Cluster] Starting 6-tier microservice ecosystem on ports 8080-8085...")
    await cluster.start()
    ready = await cluster.wait_until_ready()
    if ready:
        print("[Cluster] All 6 services READY:")
        print("  - API Gateway:          http://127.0.0.1:8080/health")
        print("  - Order Service:        http://127.0.0.1:8081/health")
        print("  - Payment Service:      http://127.0.0.1:8082/health")
        print("  - Inventory Service:    http://127.0.0.1:8083/health")
        print("  - Auth Service:         http://127.0.0.1:8084/health")
        print("  - Notification Service: http://127.0.0.1:8085/health")
        print("[Cluster] Press Ctrl+C to terminate.")
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            print("\n[Cluster] Shutting down...")
            await cluster.stop()
            print("[Cluster] Terminated.")
    else:
        print("[Cluster] Failed to reach READY state.")
        await cluster.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_cluster_cli())
    except KeyboardInterrupt:
        sys.exit(0)
