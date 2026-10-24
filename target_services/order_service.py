"""Order microservice coordinating inventory reservation and payment processing."""

import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from target_services.client import TracedAsyncClient
from target_services.tracer import TraceContextMiddleware

app = FastAPI(title="Order Service", version="1.0.0")
app.add_middleware(TraceContextMiddleware, service_name="order-service")

INVENTORY_URL = os.environ.get("INVENTORY_SERVICE_URL", "http://127.0.0.1:8083")
PAYMENT_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://127.0.0.1:8082")
NOTIFICATION_URL = os.environ.get("NOTIFICATION_SERVICE_URL", "http://127.0.0.1:8085")

client = TracedAsyncClient(service_name="order-service", timeout=5.0)

chaos_config = {
    "force_error": False,
}


class OrderItem(BaseModel):
    item_id: str
    quantity: int = Field(default=1, ge=1)


class OrderRequest(BaseModel):
    order_id: str
    items: List[OrderItem]
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD")


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": "order-service",
        "inventory_url": INVENTORY_URL,
        "payment_url": PAYMENT_URL,
        "chaos_active": chaos_config["force_error"],
    }


@app.post("/orders/process")
async def process_order(req: OrderRequest):
    if chaos_config["force_error"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chaos induced order processing failure.",
        )

    # 1. Step 1: Reserve Inventory
    inv_payload = {
        "order_id": req.order_id,
        "items": [item.model_dump() for item in req.items],
    }
    inv_resp = await client.post(f"{INVENTORY_URL}/inventory/reserve", json_data=inv_payload)
    if inv_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "step": "INVENTORY_RESERVATION",
                "status_code": inv_resp.status_code,
                "error": inv_resp.text,
            },
        )

    # 2. Step 2: Process Payment
    pay_payload = {
        "order_id": req.order_id,
        "amount": req.amount,
        "currency": req.currency,
    }
    pay_resp = await client.post(f"{PAYMENT_URL}/payments/charge", json_data=pay_payload)
    if pay_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "step": "PAYMENT_CHARGE",
                "status_code": pay_resp.status_code,
                "error": pay_resp.json() if "application/json" in pay_resp.headers.get("content-type", "") else pay_resp.text,
            },
        )

    # 3. Step 3: Trigger asynchronous notification
    notification_data = {"status": "SKIPPED"}
    try:
        notif_resp = await client.post(
            f"{NOTIFICATION_URL}/notifications/send",
            json_data={
                "order_id": req.order_id,
                "recipient": "customer@traceheal.enterprise",
                "channel": "EMAIL",
            },
        )
        if notif_resp.status_code == 200:
            notification_data = notif_resp.json()
        elif notif_resp.status_code >= 500:
            notification_data = {"status": "DEGRADED", "error": notif_resp.text}
    except Exception:
        pass

    return {
        "order_id": req.order_id,
        "status": "CONFIRMED",
        "inventory": inv_resp.json(),
        "payment": pay_resp.json(),
        "notification": notification_data,
    }


@app.post("/chaos/inject")
async def inject_chaos(force_error: bool = True):
    chaos_config["force_error"] = force_error
    return {"status": "CHAOS_INJECTED", "config": chaos_config}


@app.post("/chaos/reset")
async def reset_chaos():
    chaos_config["force_error"] = False
    return {"status": "CHAOS_RESET", "config": chaos_config}
