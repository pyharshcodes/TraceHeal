"""Inventory microservice providing stock reservation and health status."""

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from target_services.tracer import TraceContextMiddleware

app = FastAPI(title="Inventory Service", version="1.0.0")
app.add_middleware(TraceContextMiddleware, service_name="inventory-service")

# In-memory inventory state
INVENTORY_STOCK: Dict[str, int] = {
    "item-101": 500,
    "item-102": 250,
    "item-103": 100,
    "item-default": 1000,
}

# Chaos parameters for inventory
chaos_config = {
    "latency_sec": 0.0,
    "force_error": False,
}


class ReserveItem(BaseModel):
    item_id: str
    quantity: int = Field(default=1, ge=1)


class ReserveRequest(BaseModel):
    order_id: str
    items: List[ReserveItem]


class ChaosRequest(BaseModel):
    latency_sec: Optional[float] = 0.0
    force_error: Optional[bool] = False


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": "inventory-service",
        "chaos_active": chaos_config["force_error"] or chaos_config["latency_sec"] > 0,
    }


@app.post("/inventory/reserve")
async def reserve_stock(req: ReserveRequest):
    if chaos_config["latency_sec"] > 0:
        await asyncio.sleep(chaos_config["latency_sec"])

    if chaos_config["force_error"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chaos induced inventory failure: Database warehouse deadlock.",
        )

    reserved = []
    for item in req.items:
        current_stock = INVENTORY_STOCK.get(item.item_id, INVENTORY_STOCK["item-default"])
        if current_stock < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient inventory for {item.item_id}: available {current_stock}, requested {item.quantity}",
            )
        # Deduct
        INVENTORY_STOCK[item.item_id] = current_stock - item.quantity
        reserved.append({"item_id": item.item_id, "quantity": item.quantity})

    return {
        "status": "RESERVED",
        "order_id": req.order_id,
        "reserved_items": reserved,
    }


@app.post("/chaos/inject")
async def inject_chaos(req: ChaosRequest):
    chaos_config["latency_sec"] = req.latency_sec or 0.0
    chaos_config["force_error"] = bool(req.force_error)
    return {"status": "CHAOS_INJECTED", "config": chaos_config}


@app.post("/chaos/reset")
async def reset_chaos():
    chaos_config["latency_sec"] = 0.0
    chaos_config["force_error"] = False
    return {"status": "CHAOS_RESET", "config": chaos_config}


class RemediateInventoryRequest(BaseModel):
    latency_sec: Optional[float] = None
    force_error: Optional[bool] = None
    replenish_stock: Optional[Dict[str, int]] = None


@app.post("/config/remediate")
async def remediate_config(req: RemediateInventoryRequest):
    applied = {}
    if req.latency_sec is not None:
        chaos_config["latency_sec"] = req.latency_sec
        applied["latency_sec"] = req.latency_sec
    if req.force_error is not None:
        chaos_config["force_error"] = req.force_error
        applied["force_error"] = req.force_error
    if req.replenish_stock:
        INVENTORY_STOCK.update(req.replenish_stock)
        applied["replenish_stock"] = req.replenish_stock

    return {
        "status": "CONFIG_APPLIED",
        "service": "inventory-service",
        "applied": applied,
        "config": chaos_config,
    }


@app.get("/config/state")
async def get_config_state():
    return {
        "service": "inventory-service",
        "chaos_config": chaos_config,
        "stock": INVENTORY_STOCK,
    }
