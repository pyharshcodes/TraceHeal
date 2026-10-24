"""Remediation Orchestrator, Shadow Validator & Deployment Engine.

Coordinates shadow sandbox validation, human-in-the-loop approval gates,
and safe deployment with automated health verification and canary rollback.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AuditEvent, Hypothesis, Incident, Remediation, utc_now
from backend.app.incidents.service import IncidentService
from backend.app.remediation.policy_engine import PolicyEngine
from backend.app.remediation.shadow_validator import ShadowValidator
from backend.app.schemas.remediation import PolicyCheckResult, ShadowValidationResult

SERVICE_DEFAULT_URLS = {
    "gateway-service": "http://127.0.0.1:8080",
    "order-service": "http://127.0.0.1:8081",
    "payment-service": "http://127.0.0.1:8082",
    "inventory-service": "http://127.0.0.1:8083",
    "auth-service": "http://127.0.0.1:8084",
    "notification-service": "http://127.0.0.1:8085",
}


def _extract_config_params(remediation: Remediation) -> Dict[str, Any]:
    """Helper to derive config parameters for target service endpoints."""
    target = remediation.target_service
    if target == "payment-service":
        return {
            "max_connections": 15,
            "acquire_timeout_sec": 0.5,
            "hold_duration_sec": 0.05,
        }
    elif target == "inventory-service":
        return {
            "force_error": False,
            "latency_sec": 0.0,
            "replenish_stock": {"item-101": 1000},
        }
    elif target == "auth-service":
        return {
            "jwks_cache_ttl": 3600,
            "grace_period_sec": 300,
            "force_token_expire": False,
        }
    elif target == "notification-service":
        return {
            "max_retries": 3,
            "backoff_base_sec": 2.0,
            "overflow_dlq": False,
        }
    return {"timeout_sec": 5.0}


def _extract_rollback_params(remediation: Remediation) -> Dict[str, Any]:
    """Helper to derive rollback parameters for target service endpoints."""
    target = remediation.target_service
    if target == "payment-service":
        return {
            "max_connections": 2,
            "acquire_timeout_sec": 0.1,
            "hold_duration_sec": 0.25,
        }
    elif target == "inventory-service":
        return {
            "force_error": True,
            "latency_sec": 2.0,
        }
    elif target == "auth-service":
        return {
            "force_token_expire": True,
        }
    elif target == "notification-service":
        return {
            "overflow_dlq": True,
        }
    return {"timeout_sec": 1.0}


class RemediationDeployer:
    """Orchestrates shadow validation, approval verification, and safe target deployment."""

    def __init__(self, shadow_validator: Optional[ShadowValidator] = None):
        self.validator = shadow_validator or ShadowValidator()

    async def execute_shadow_validation(
        self,
        db: AsyncSession,
        remediation_id: str,
    ) -> ShadowValidationResult:
        """Validates the remediation in an isolated sandbox before allowing approval."""
        stmt = select(Remediation).where(Remediation.id == remediation_id)
        res = await db.execute(stmt)
        rem = res.scalar_one_or_none()
        if not rem:
            raise ValueError(f"Remediation '{remediation_id}' not found.")

        if rem.policy_check_status != "PASSED":
            raise ValueError(f"Cannot shadow-validate remediation: policy check is '{rem.policy_check_status}'.")

        # Load linked hypothesis to get the reproduction recipe
        recipe = {}
        if rem.hypothesis_id:
            h_stmt = select(Hypothesis).where(Hypothesis.id == rem.hypothesis_id)
            h_res = await db.execute(h_stmt)
            hypo = h_res.scalar_one_or_none()
            if hypo and hypo.reproduction_recipe_json:
                try:
                    recipe = json.loads(hypo.reproduction_recipe_json)
                except Exception:
                    pass

        # If recipe is empty, construct standard verification load
        if not recipe:
            recipe = {
                "scenario": "DB_POOL_EXHAUSTION" if rem.target_service == "payment-service" else "NONE",
                "endpoint": "/payments/charge" if rem.target_service == "payment-service" else "/health",
                "concurrency": 6,
                "parameters": {"max_connections": 2, "acquire_timeout_sec": 0.1, "hold_duration_sec": 0.25},
                "expected_error_signature": "DBPoolExhaustionError",
            }

        config_params = _extract_config_params(rem)
        patch_payload = {
            "patch_type": rem.patch_type,
            "config_parameters": config_params,
        }

        # Run shadow validation inside sandbox
        val_result = await self.validator.validate_remediation(
            service_name=rem.target_service,
            remediation_patch=patch_payload,
            reproduction_recipe=recipe,
        )

        rem.validation_status = val_result.status
        rem.validation_details_json = json.dumps(val_result.model_dump())

        event_name = "REMEDIATION_SHADOW_VALIDATED" if val_result.status == "VALIDATED" else "REMEDIATION_SHADOW_FAILED"
        audit = AuditEvent(
            incident_id=rem.incident_id,
            event_type=event_name,
            actor="SHADOW_VALIDATOR",
            details_json=json.dumps(val_result.model_dump()),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(rem)
        return val_result

    async def approve_remediation(
        self,
        db: AsyncSession,
        remediation_id: str,
        approver: str = "SRE_LEAD",
        decision: str = "APPROVE",
        notes: Optional[str] = None,
    ) -> Remediation:
        """Applies human-in-the-loop approval or rejection."""
        stmt = select(Remediation).where(Remediation.id == remediation_id)
        res = await db.execute(stmt)
        rem = res.scalar_one_or_none()
        if not rem:
            raise ValueError(f"Remediation '{remediation_id}' not found.")

        if decision == "APPROVE":
            if rem.policy_check_status != "PASSED":
                raise ValueError("Cannot approve remediation: policy check must be 'PASSED'.")
            if rem.validation_status != "VALIDATED":
                raise ValueError("Cannot approve remediation: shadow validation must be 'VALIDATED'.")

            rem.approval_status = "APPROVED"
            audit_type = "REMEDIATION_APPROVED"
        else:
            rem.approval_status = "REJECTED"
            audit_type = "REMEDIATION_REJECTED"

        audit = AuditEvent(
            incident_id=rem.incident_id,
            event_type=audit_type,
            actor=approver,
            details_json=json.dumps({"notes": notes, "decision": decision}),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(rem)
        return rem

    async def apply_remediation(
        self,
        db: AsyncSession,
        remediation_id: str,
        target_base_url: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Deploys an approved remediation to the live service with automatic rollback safety."""
        stmt = select(Remediation).where(Remediation.id == remediation_id)
        res = await db.execute(stmt)
        rem = res.scalar_one_or_none()
        if not rem:
            raise ValueError(f"Remediation '{remediation_id}' not found.")

        if not force and rem.approval_status != "APPROVED":
            raise ValueError(f"Remediation '{remediation_id}' must be 'APPROVED' prior to live deployment.")

        base_url = target_base_url or SERVICE_DEFAULT_URLS.get(rem.target_service)
        if not base_url:
            raise ValueError(f"No target URL configured for service '{rem.target_service}'.")

        config_params = _extract_config_params(rem)

        # 1. Apply patch to live service
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                apply_resp = await client.post(f"{base_url}/config/remediate", json=config_params)
                if apply_resp.status_code != 200:
                    raise RuntimeError(f"Service returned error applying patch: {apply_resp.status_code} - {apply_resp.text}")

                # 2. Post-deployment health verification
                health_resp = await client.get(f"{base_url}/health")
                if health_resp.status_code != 200:
                    raise RuntimeError(f"Post-deployment health check failed: {health_resp.status_code}")

        except Exception as deploy_err:
            # Trigger Automated Rollback
            rollback_params = _extract_rollback_params(rem)
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(f"{base_url}/config/remediate", json=rollback_params)
            except Exception:
                pass

            audit = AuditEvent(
                incident_id=rem.incident_id,
                event_type="REMEDIATION_ROLLBACK_AUTOMATED",
                actor="DEPLOYER_ORCHESTRATOR",
                details_json=json.dumps({"error": str(deploy_err), "target": base_url}),
            )
            db.add(audit)
            await db.commit()
            raise RuntimeError(f"Live deployment failed and automated rollback triggered: {deploy_err}")

        # 3. Mark remediation applied
        rem.applied_at = utc_now()

        # 4. Advance incident state machine to REMEDIATED
        await IncidentService.update_incident_status(
            db=db,
            incident_id=rem.incident_id,
            new_status="REMEDIATED",
            actor="DEPLOYER_ORCHESTRATOR",
            details={"remediation_id": rem.id, "target_url": base_url},
        )

        audit = AuditEvent(
            incident_id=rem.incident_id,
            event_type="REMEDIATION_APPLIED",
            actor="DEPLOYER_ORCHESTRATOR",
            details_json=json.dumps({"target_url": base_url, "applied_params": config_params}),
        )
        db.add(audit)

        await db.commit()
        await db.refresh(rem)

        return {
            "status": "APPLIED",
            "remediation_id": rem.id,
            "target_service": rem.target_service,
            "target_url": base_url,
            "applied_at": rem.applied_at.isoformat(),
            "incident_status": "REMEDIATED",
        }

    async def rollback_remediation(
        self,
        db: AsyncSession,
        remediation_id: str,
        target_base_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes explicit rollback of an applied remediation."""
        stmt = select(Remediation).where(Remediation.id == remediation_id)
        res = await db.execute(stmt)
        rem = res.scalar_one_or_none()
        if not rem:
            raise ValueError(f"Remediation '{remediation_id}' not found.")

        base_url = target_base_url or SERVICE_DEFAULT_URLS.get(rem.target_service)
        rollback_params = _extract_rollback_params(rem)

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(f"{base_url}/config/remediate", json=rollback_params)
            if resp.status_code != 200:
                raise RuntimeError(f"Rollback call failed: {resp.status_code} - {resp.text}")

        audit = AuditEvent(
            incident_id=rem.incident_id,
            event_type="REMEDIATION_ROLLBACK_MANUAL",
            actor="OPERATOR_ROLLBACK",
            details_json=json.dumps({"target_url": base_url, "rollback_params": rollback_params}),
        )
        db.add(audit)
        await db.commit()

        return {
            "status": "ROLLED_BACK",
            "remediation_id": rem.id,
            "target_service": rem.target_service,
            "rollback_applied": rollback_params,
        }
