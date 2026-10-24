"""Notification microservice handling asynchronous message queue delivery (SMS/Email/Push)."""

import asyncio
import os
import time
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from target_services.tracer import TraceContextMiddleware

app = FastAPI(title="Notification Service", version="1.0.0")
app.add_middleware(TraceContextMiddleware, service_name="notification-service")

chaos_config = {
    "force_error": False,
    "latency_sec": 0.0,
    "queue_overflow": False,
}


class NotificationRequest(BaseModel):
    order_id: str
    recipient: str = Field(default="customer@traceheal.enterprise")
    channel: str = Field(default="EMAIL")
    message: Optional[str] = None


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": "notification-service",
        "queue_depth": 0,
        "dispatched_total": 528,
        "chaos_active": chaos_config["force_error"] or chaos_config["queue_overflow"] or chaos_config["latency_sec"] > 0,
    }


@app.post("/notifications/send")
async def send_notification(req: NotificationRequest):
    """Dispatches asynchronous notification to message queue."""
    if chaos_config["latency_sec"] > 0:
        await asyncio.sleep(chaos_config["latency_sec"])

    if chaos_config["force_error"] or chaos_config["queue_overflow"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DeadLetterQueueOverflowError: Upstream SMTP retry storm saturated dispatch worker pool.",
        )

    msg_id = f"msg_{os.urandom(4).hex()}"
    return {
        "status": "DELIVERED",
        "message_id": msg_id,
        "order_id": req.order_id,
        "recipient": req.recipient,
        "channel": req.channel,
        "dispatched_at": time.time(),
    }


class NotificationChaosRequest(BaseModel):
    force_error: bool = False
    latency_sec: float = 0.0
    queue_overflow: bool = False


@app.post("/chaos/inject")
async def inject_chaos(req: Optional[NotificationChaosRequest] = None):
    if req:
        chaos_config["force_error"] = req.force_error
        chaos_config["latency_sec"] = req.latency_sec
        chaos_config["queue_overflow"] = req.queue_overflow
    else:
        chaos_config["force_error"] = True
    return {"status": "CHAOS_INJECTED", "config": chaos_config}


@app.post("/chaos/reset")
async def reset_chaos():
    chaos_config["force_error"] = False
    chaos_config["latency_sec"] = 0.0
    chaos_config["queue_overflow"] = False
    return {"status": "CHAOS_RESET", "config": chaos_config}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("target_services.notification_service:app", host="127.0.0.1", port=8085, reload=True)
