"""Auth microservice providing distributed token validation and session security."""

import asyncio
import os
import time
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Header, status
from pydantic import BaseModel, Field

from target_services.tracer import TraceContextMiddleware

app = FastAPI(title="Auth Service", version="1.0.0")
app.add_middleware(TraceContextMiddleware, service_name="auth-service")

chaos_config = {
    "force_error": False,
    "latency_sec": 0.0,
    "expire_all": False,
}


class TokenVerifyRequest(BaseModel):
    token: Optional[str] = Field(default="jwt_session_valid_mock")
    client_id: Optional[str] = Field(default="web-storefront")


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": "auth-service",
        "active_tokens": 256,
        "chaos_active": chaos_config["force_error"] or chaos_config["latency_sec"] > 0,
    }


@app.post("/auth/verify-token")
async def verify_token(req: Optional[TokenVerifyRequest] = None):
    """Verifies incoming session token or bearer identity."""
    if chaos_config["latency_sec"] > 0:
        await asyncio.sleep(chaos_config["latency_sec"])

    if chaos_config["force_error"] or chaos_config["expire_all"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TokenExpiredOrRevokedError: JWKS certificate validation failed under upstream rotation.",
        )

    return {
        "valid": True,
        "user_id": "usr_shopper_01",
        "role": "CUSTOMER",
        "session_ttl_sec": 3600,
        "verified_at": time.time(),
    }


class AuthChaosRequest(BaseModel):
    force_error: bool = False
    latency_sec: float = 0.0
    expire_all: bool = False


@app.post("/chaos/inject")
async def inject_chaos(req: Optional[AuthChaosRequest] = None):
    if req:
        chaos_config["force_error"] = req.force_error
        chaos_config["latency_sec"] = req.latency_sec
        chaos_config["expire_all"] = req.expire_all
    else:
        chaos_config["force_error"] = True
    return {"status": "CHAOS_INJECTED", "config": chaos_config}


@app.post("/chaos/reset")
async def reset_chaos():
    chaos_config["force_error"] = False
    chaos_config["latency_sec"] = 0.0
    chaos_config["expire_all"] = False
    return {"status": "CHAOS_RESET", "config": chaos_config}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("target_services.auth_service:app", host="127.0.0.1", port=8084, reload=True)
