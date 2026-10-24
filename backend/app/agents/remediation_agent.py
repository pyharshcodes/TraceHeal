"""Remediation Agent.

Autonomous agent that synthesizes actionable, policy-checked configuration and code
remediation proposals from verified empirical root causes.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AuditEvent, Hypothesis, Incident, Remediation
from backend.app.llm.client import hybrid_llm_client
from backend.app.remediation.policy_engine import PolicyEngine


class RemediationAgent:
    """Agent that analyzes verified root causes and synthesizes concrete remediations."""

    async def propose_remediation(
        self,
        db: AsyncSession,
        incident_id: str,
        hypothesis_id: Optional[str] = None,
    ) -> Remediation:
        """Synthesizes a policy-checked remediation proposal for a verified incident."""
        # 1. Fetch incident
        stmt = select(Incident).where(Incident.id == incident_id)
        res = await db.execute(stmt)
        incident = res.scalar_one_or_none()
        if not incident:
            raise ValueError(f"Incident '{incident_id}' not found.")

        # 2. Fetch hypothesis
        hypo: Optional[Hypothesis] = None
        if hypothesis_id:
            h_stmt = select(Hypothesis).where(Hypothesis.id == hypothesis_id)
            h_res = await db.execute(h_stmt)
            hypo = h_res.scalar_one_or_none()
        else:
            # Look for verified hypothesis first, or top ranked
            for h in incident.hypotheses:
                if h.status == "VERIFIED":
                    hypo = h
                    break
            if not hypo and incident.hypotheses:
                hypo = incident.hypotheses[0]

        if not hypo:
            raise ValueError(f"No hypothesis available for incident '{incident_id}'.")

        target_service = hypo.suspect_service or incident.suspect_service
        recipe = {}
        if hypo.reproduction_recipe_json:
            try:
                recipe = json.loads(hypo.reproduction_recipe_json)
            except Exception:
                recipe = {}

        # 3. Synthesize patch parameters and diffs using Hybrid LLM Reasoning Engine
        scenario = recipe.get("scenario", "NONE")
        remediation_synth = await hybrid_llm_client.synthesize_remediation_diff(
            service_name=target_service,
            hypothesis_title=hypo.title or "Failure",
            proposed_cause=hypo.proposed_cause or "Fault",
            scenario=scenario,
        )
        patch_type = remediation_synth.get("patch_type", "CONFIG")
        config_params = remediation_synth.get("config_parameters", {})
        diff_content = remediation_synth.get("diff_content", "")
        rollback_diff = remediation_synth.get("rollback_diff", "")

        # 4. Evaluate Safety & Security Policy
        policy_result = PolicyEngine.evaluate(
            target_service=target_service,
            diff_content=diff_content,
            patch_type=patch_type,
            config_parameters=config_params,
            rollback_diff=rollback_diff,
        )

        violations_json = json.dumps(policy_result.violations) if policy_result.violations else None

        # 5. Create Remediation model record
        remediation = Remediation(
            incident_id=incident.id,
            hypothesis_id=hypo.id,
            patch_type=patch_type,
            target_service=target_service,
            diff_content=diff_content,
            rollback_diff=rollback_diff,
            policy_check_status=policy_result.status,
            policy_violations_json=violations_json,
            validation_status="PENDING",
            approval_status="PENDING_APPROVAL",
        )
        db.add(remediation)

        # 6. Audit Trail Event
        audit = AuditEvent(
            incident_id=incident.id,
            event_type="REMEDIATION_PROPOSED",
            actor="AGENT_REMEDIATION",
            details_json=json.dumps({
                "hypothesis_id": hypo.id,
                "target_service": target_service,
                "patch_type": patch_type,
                "policy_status": policy_result.status,
                "config_params": config_params,
            }),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(remediation)
        return remediation
