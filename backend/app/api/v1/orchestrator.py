"""Autonomous Lifecycle Orchestrator API Endpoints."""

from typing import Any, Dict
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db
from backend.app.orchestrator.lifecycle import AutonomousLifecycleOrchestrator

router = APIRouter(prefix="/orchestrator", tags=["Autonomous Orchestrator"])
orchestrator = AutonomousLifecycleOrchestrator()


class RunCycleRequest(BaseModel):
    scenario: str = Field(default="DB_POOL_EXHAUSTION", description="Chaos failure mode to execute")
    target_service: str = Field(default="payment-service", description="Target microservice name")
    trace_count: int = Field(default=3, description="Number of failure traces to synthesize")
    live_cluster: bool = Field(default=False, description="Attempt live network verification if microservices are running")


@router.post("/run-cycle")
async def run_autonomous_cycle(req: RunCycleRequest, db: AsyncSession = Depends(get_db)):
    """Executes the full end-to-end closed-loop autonomous remediation cycle:

    Trace -> Hypothesize -> Reproduce -> Verify -> Remediate -> Validate -> Postmortem & PR -> Close.
    """
    manifest = await orchestrator.run_full_autonomous_cycle(
        db=db,
        scenario=req.scenario,
        target_service=req.target_service,
        trace_count=req.trace_count,
        live_cluster=req.live_cluster,
    )
    return manifest
