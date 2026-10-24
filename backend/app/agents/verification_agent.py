"""Autonomous Empirical Hypothesis Verification Agent.

Coordinates ephemeral sandbox provisioning, synthetic failure replay,
and evidence-based verification or refutation of causal hypotheses.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AuditEvent, Hypothesis, Incident, SandboxRun
from backend.app.incidents.service import transition_incident_status
from backend.app.sandbox.reproduction import ReproductionExecutor
from backend.app.sandbox.runner import ProcessSandboxRunner


class VerificationAgent:
    """Orchestrates empirical sandbox verification for root cause hypotheses."""

    def __init__(self, runner: Optional[ProcessSandboxRunner] = None):
        self.runner = runner or ProcessSandboxRunner()
        self.executor = ReproductionExecutor()

    def _extract_recipe(self, hypothesis: Hypothesis) -> Dict[str, Any]:
        """Extracts structured reproduction recipe JSON from hypothesis evidence."""
        summary = hypothesis.evidence_summary or ""
        marker = "Reproduction Recipe:"
        if marker in summary:
            json_str = summary.split(marker, 1)[1].strip()
            try:
                return json.loads(json_str)
            except Exception:
                pass

        # Fallback default recipe based on suspect service
        svc = hypothesis.suspect_service
        if "payment" in svc:
            return {
                "target_service": svc,
                "scenario": "DB_POOL_EXHAUSTION",
                "endpoint": "/payments/charge",
                "concurrency": 8,
                "parameters": {"max_connections": 2, "acquire_timeout_sec": 0.1, "hold_duration_sec": 0.25},
                "expected_error_signature": "DBPoolExhaustionError",
            }
        return {
            "target_service": svc,
            "scenario": "NONE",
            "endpoint": "/health",
            "concurrency": 1,
            "parameters": {},
            "expected_error_signature": "Error",
        }

    async def verify_hypothesis(
        self,
        db: AsyncSession,
        hypothesis_id: str,
    ) -> Tuple[Hypothesis, SandboxRun]:
        """Executes full empirical verification loop inside an isolated sandbox."""
        # 1. Fetch hypothesis & incident
        stmt = select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        result = await db.execute(stmt)
        hypothesis = result.scalar_one_or_none()
        if not hypothesis:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found.")

        incident_stmt = select(Incident).where(Incident.id == hypothesis.incident_id)
        inc_res = await db.execute(incident_stmt)
        incident = inc_res.scalar_one_or_none()
        if not incident:
            raise ValueError(f"Incident for hypothesis '{hypothesis_id}' not found.")

        recipe = self._extract_recipe(hypothesis)
        suspect_svc = hypothesis.suspect_service

        # 2. Transition incident to REPRODUCING
        if incident.status == "INVESTIGATING":
            await transition_incident_status(
                db,
                incident.id,
                "REPRODUCING",
                actor="AGENT_VERIFICATION",
                reason=f"Spinning up isolated sandbox for hypothesis {hypothesis_id}",
            )

        # 3. Create SandboxRun record in DB
        sandbox_run = SandboxRun(
            incident_id=incident.id,
            hypothesis_id=hypothesis.id,
            service_name=suspect_svc,
            sandbox_type="PROCESS",
            port=0,
            status="PENDING",
            reproduction_verified=False,
        )
        db.add(sandbox_run)
        await db.commit()
        await db.refresh(sandbox_run)

        # 4. Provision isolated Sandbox environment
        env = await self.runner.create_sandbox(suspect_svc)
        sandbox_run.port = env.port
        sandbox_run.status = "RUNNING"
        await db.commit()

        try:
            # 5. Replay reproduction recipe
            exec_result = await self.executor.execute_recipe(env, recipe)

            # 6. Evaluate verification
            sandbox_run.exit_code = exec_result.exit_code
            sandbox_run.reproduction_verified = exec_result.reproduction_verified
            sandbox_run.reproduction_signature = exec_result.observed_signature
            sandbox_run.stdout_log = json.dumps(exec_result.details)
            sandbox_run.finished_at = datetime.now(timezone.utc)

            if exec_result.reproduction_verified:
                sandbox_run.status = "SUCCESS"
                hypothesis.status = "VERIFIED"

                # Transition incident to VERIFIED
                await transition_incident_status(
                    db,
                    incident.id,
                    "VERIFIED",
                    actor="AGENT_VERIFICATION",
                    reason=f"Empirical reproduction verified failure signature: {exec_result.observed_signature[:64]}",
                )

                audit = AuditEvent(
                    incident_id=incident.id,
                    event_type="HYPOTHESIS_VERIFIED",
                    actor="AGENT_VERIFICATION",
                    details_json=json.dumps({
                        "hypothesis_id": hypothesis.id,
                        "sandbox_run_id": sandbox_run.id,
                        "reproduced_signature": exec_result.observed_signature,
                        "reproduction_verified": True,
                    }),
                )
                db.add(audit)
                incident.audit_events.append(audit)
            else:
                sandbox_run.status = "FAILED"
                hypothesis.status = "REFUTED"

                # Transition incident back to INVESTIGATING
                await transition_incident_status(
                    db,
                    incident.id,
                    "INVESTIGATING",
                    actor="AGENT_VERIFICATION",
                    reason="Reproduction attempt refuted hypothesis. Returning to investigation.",
                )

                audit = AuditEvent(
                    incident_id=incident.id,
                    event_type="HYPOTHESIS_REFUTED",
                    actor="AGENT_VERIFICATION",
                    details_json=json.dumps({
                        "hypothesis_id": hypothesis.id,
                        "sandbox_run_id": sandbox_run.id,
                        "reproduction_verified": False,
                    }),
                )
                db.add(audit)
                incident.audit_events.append(audit)

            await db.commit()
            await db.refresh(hypothesis)
            await db.refresh(sandbox_run)
            await db.refresh(incident, ["audit_events"])
            return hypothesis, sandbox_run

        finally:
            # 7. Always tear down sandbox environment
            await self.runner.destroy_sandbox(env)
