"""Traffic Generator & Anomaly Daemon API Endpoints."""

from typing import Any, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.incidents.daemon import anomaly_detector_daemon
from target_services.traffic_controller import traffic_controller

router = APIRouter(prefix="/traffic", tags=["Continuous Traffic & Autonomic Observer"])


class TrafficStartRequest(BaseModel):
    rate_rps: float = Field(default=2.0, ge=0.5, le=50.0, description="Requests per second")


@router.get("/status")
async def get_traffic_status() -> Dict[str, Any]:
    """Retrieves live telemetry for the continuous traffic generator and anomaly observer."""
    return {
        "traffic": traffic_controller.status(),
        "daemon": anomaly_detector_daemon.status(),
    }


@router.post("/start")
async def start_continuous_traffic(
    payload: Optional[TrafficStartRequest] = None,
    rate_rps: Optional[float] = None,
) -> Dict[str, Any]:
    """Starts synthetic continuous customer checkout traffic."""
    effective_rps = 2.0
    if payload and payload.rate_rps:
        effective_rps = payload.rate_rps
    elif rate_rps is not None:
        effective_rps = rate_rps
    result = await traffic_controller.start(rate_rps=effective_rps)
    return {"status": "STARTED", "traffic": result}


@router.post("/stop")
async def stop_continuous_traffic() -> Dict[str, Any]:
    """Stops synthetic customer checkout traffic."""
    result = await traffic_controller.stop()
    return {"status": "STOPPED", "traffic": result}


@router.post("/daemon/start")
async def start_anomaly_daemon() -> Dict[str, Any]:
    """Starts the background sliding-window anomaly detector daemon."""
    await anomaly_detector_daemon.start()
    return {"status": "STARTED", "daemon": anomaly_detector_daemon.status()}


@router.post("/daemon/stop")
async def stop_anomaly_daemon() -> Dict[str, Any]:
    """Stops the background sliding-window anomaly detector daemon."""
    await anomaly_detector_daemon.stop()
    return {"status": "STOPPED", "daemon": anomaly_detector_daemon.status()}
