"""Payment microservice with realistic Database Connection Pool simulation.

Demonstrates real database pool exhaustion and unhandled timeout failure modes.
"""

import asyncio
import secrets
import time
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from target_services.tracer import TraceContextMiddleware

app = FastAPI(title="Payment Service", version="1.0.0")
app.add_middleware(TraceContextMiddleware, service_name="payment-service")


class DBPoolExhaustionError(Exception):
    """Raised when all database connections are in use and acquire times out."""
    pass


class SimulatedDatabasePool:
    """Simulates an enterprise PostgreSQL connection pool (HikariCP / SQLAlchemy style).

    Supports dynamic pool resizing, connection acquisition timeouts, and concurrency throttling.
    """

    def __init__(self, max_connections: int = 10, acquire_timeout_sec: float = 0.3):
        self.max_connections = max_connections
        self.acquire_timeout_sec = acquire_timeout_sec
        self.active_connections = 0
        self._lock = asyncio.Lock()

    def resize(self, new_max: int, acquire_timeout: Optional[float] = None, acquire_timeout_sec: Optional[float] = None):
        """Dynamically reconfigures the connection pool capacity."""
        self.max_connections = new_max
        timeout = acquire_timeout if acquire_timeout is not None else acquire_timeout_sec
        if timeout is not None:
            self.acquire_timeout_sec = timeout
        self.active_connections = 0

    async def acquire(self):
        """Attempts to acquire a database connection within acquire_timeout_sec."""
        start_t = time.time()
        while True:
            async with self._lock:
                if self.active_connections < self.max_connections:
                    self.active_connections += 1
                    return self

            if (time.time() - start_t) >= self.acquire_timeout_sec:
                raise DBPoolExhaustionError(
                    f"Timeout acquiring connection from database pool within {int(self.acquire_timeout_sec * 1000)}ms "
                    f"(active: {self.active_connections}, max: {self.max_connections})"
                )
            await asyncio.sleep(0.01)

    async def release(self):
        """Releases the connection back to the pool."""
        async with self._lock:
            self.active_connections = max(0, self.active_connections - 1)


# Global database pool instance (default 10 connections)
db_pool = SimulatedDatabasePool(max_connections=10, acquire_timeout_sec=0.3)

# Chaos parameters for payment service
chaos_config = {
    "scenario": "NONE",
    "hold_duration_sec": 0.02,  # Normal SQL query execution duration
    "extra_latency_sec": 0.0,
    "force_deadlock": False,
}


class ChargeRequest(BaseModel):
    order_id: str
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD")


class PaymentChaosRequest(BaseModel):
    scenario: Optional[str] = "DB_POOL_EXHAUSTION"
    max_connections: Optional[int] = 2
    acquire_timeout_sec: Optional[float] = 0.25
    hold_duration_sec: Optional[float] = 0.4
    extra_latency_sec: Optional[float] = 0.0
    force_deadlock: Optional[bool] = False


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": "payment-service",
        "pool": {
            "active_connections": db_pool.active_connections,
            "max_connections": db_pool.max_connections,
            "acquire_timeout_sec": db_pool.acquire_timeout_sec,
        },
        "chaos_config": chaos_config,
    }


@app.post("/payments/charge")
async def process_payment(req: ChargeRequest):
    if chaos_config["extra_latency_sec"] > 0:
        await asyncio.sleep(chaos_config["extra_latency_sec"])

    if chaos_config["force_deadlock"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DeadlockDetectedError: Transaction deadlock during payment settlement lock.",
        )

    # Acquire connection from pool
    try:
        conn = await db_pool.acquire()
    except DBPoolExhaustionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "DBPoolExhaustionError",
                "message": str(exc),
                "service": "payment-service",
                "component": "PostgreSQLConnectionPool",
                "active_connections": db_pool.active_connections,
                "max_connections": db_pool.max_connections,
            },
        )

    try:
        # Simulate SQL transaction execution (hold connection)
        hold_time = chaos_config["hold_duration_sec"]
        await asyncio.sleep(hold_time)

        payment_id = f"pay_{secrets.token_hex(6)}"
        return {
            "status": "CHARGED",
            "payment_id": payment_id,
            "order_id": req.order_id,
            "amount": req.amount,
            "currency": req.currency,
            "timestamp": time.time(),
        }
    finally:
        await conn.release()


@app.post("/chaos/inject")
async def inject_chaos(req: PaymentChaosRequest):
    scenario = req.scenario or "DB_POOL_EXHAUSTION"
    chaos_config["scenario"] = scenario
    chaos_config["hold_duration_sec"] = req.hold_duration_sec or 0.4
    chaos_config["extra_latency_sec"] = req.extra_latency_sec or 0.0
    chaos_config["force_deadlock"] = bool(req.force_deadlock)

    if scenario == "DB_POOL_EXHAUSTION":
        new_max = req.max_connections if req.max_connections is not None else 2
        timeout = req.acquire_timeout_sec if req.acquire_timeout_sec is not None else 0.25
        db_pool.resize(new_max=new_max, acquire_timeout=timeout)

    return {
        "status": "CHAOS_INJECTED",
        "scenario": scenario,
        "pool": {
            "max_connections": db_pool.max_connections,
            "acquire_timeout_sec": db_pool.acquire_timeout_sec,
        },
        "chaos_config": chaos_config,
    }


@app.post("/chaos/reset")
async def reset_chaos():
    chaos_config["scenario"] = "NONE"
    chaos_config["hold_duration_sec"] = 0.02
    chaos_config["extra_latency_sec"] = 0.0
    chaos_config["force_deadlock"] = False
    db_pool.resize(new_max=10, acquire_timeout_sec=0.3)
    return {
        "status": "CHAOS_RESET",
        "pool": {
            "max_connections": db_pool.max_connections,
            "acquire_timeout_sec": db_pool.acquire_timeout_sec,
        },
        "chaos_config": chaos_config,
    }


class RemediateConfigRequest(BaseModel):
    max_connections: Optional[int] = None
    acquire_timeout_sec: Optional[float] = None
    hold_duration_sec: Optional[float] = None
    extra_latency_sec: Optional[float] = None


@app.post("/config/remediate")
async def remediate_config(req: RemediateConfigRequest):
    applied = {}
    if req.max_connections is not None:
        db_pool.resize(
            new_max=req.max_connections,
            acquire_timeout=req.acquire_timeout_sec or db_pool.acquire_timeout_sec
        )
        applied["max_connections"] = req.max_connections
    elif req.acquire_timeout_sec is not None:
        db_pool.resize(
            new_max=db_pool.max_connections,
            acquire_timeout=req.acquire_timeout_sec
        )
        applied["acquire_timeout_sec"] = req.acquire_timeout_sec

    if req.hold_duration_sec is not None:
        chaos_config["hold_duration_sec"] = req.hold_duration_sec
        applied["hold_duration_sec"] = req.hold_duration_sec
    if req.extra_latency_sec is not None:
        chaos_config["extra_latency_sec"] = req.extra_latency_sec
        applied["extra_latency_sec"] = req.extra_latency_sec

    if db_pool.max_connections >= 10:
        chaos_config["scenario"] = "NONE"

    return {
        "status": "CONFIG_APPLIED",
        "service": "payment-service",
        "applied": applied,
        "pool": {
            "max_connections": db_pool.max_connections,
            "acquire_timeout_sec": db_pool.acquire_timeout_sec,
            "active_connections": db_pool.active_connections,
        },
        "chaos_config": chaos_config,
    }


@app.get("/config/state")
async def get_config_state():
    return {
        "service": "payment-service",
        "pool": {
            "max_connections": db_pool.max_connections,
            "acquire_timeout_sec": db_pool.acquire_timeout_sec,
            "active_connections": db_pool.active_connections,
        },
        "chaos_config": chaos_config,
    }
