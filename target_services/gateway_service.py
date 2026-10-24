"""API Gateway service providing external entry point and routing to order-service."""

import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from target_services.client import TracedAsyncClient
from target_services.tracer import TraceContextMiddleware

app = FastAPI(title="API Gateway", version="1.0.0")
app.add_middleware(TraceContextMiddleware, service_name="gateway-service")

ORDER_URL = os.environ.get("ORDER_SERVICE_URL", "http://127.0.0.1:8081")
AUTH_URL = os.environ.get("AUTH_SERVICE_URL", "http://127.0.0.1:8084")

client = TracedAsyncClient(service_name="gateway-service", timeout=5.0)


class CheckoutItem(BaseModel):
    item_id: str
    quantity: int = Field(default=1, ge=1)


class CheckoutRequest(BaseModel):
    order_id: Optional[str] = None
    items: List[CheckoutItem]
    amount: float = Field(..., gt=0)
    currency: str = Field(default="USD")


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": "gateway-service",
        "order_url": ORDER_URL,
    }


@app.post("/api/v1/orders/checkout")
async def checkout(req: CheckoutRequest):
    order_id = req.order_id or f"ord_{os.urandom(4).hex()}"

    # Step 0: Verify session token with auth-service if reachable
    try:
        auth_resp = await client.post(f"{AUTH_URL}/auth/verify-token", json_data={"token": "tok_session_valid"})
        if auth_resp.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "AuthenticationFailed", "details": auth_resp.json()},
            )
    except HTTPException:
        raise
    except Exception:
        # Graceful fallback if auth-service is not deployed in minimal test environments
        pass

    payload = {
        "order_id": order_id,
        "items": [item.model_dump() for item in req.items],
        "amount": req.amount,
        "currency": req.currency,
    }

    resp = await client.post(f"{ORDER_URL}/orders/process", json_data=payload)
    if resp.status_code != 200:
        error_content = resp.json() if "application/json" in resp.headers.get("content-type", "") else resp.text
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "GatewayCheckoutFailed",
                "downstream_status": resp.status_code,
                "details": error_content,
            },
        )

    return resp.json()


@app.get("/collector/spans", include_in_schema=False)
async def get_collector_spans():
    from target_services.tracer import collector
    return collector._spans


@app.post("/collector/clear", include_in_schema=False)
async def clear_collector_spans():
    from target_services.tracer import collector
    collector._spans.clear()
    return {"status": "CLEARED"}
