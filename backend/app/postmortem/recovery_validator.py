"""Post-Remediation Cluster Recovery Validator.

Sends verification traffic to target services post-remediation to empirically
confirm service health and error-free operation, transitioning incident to RESOLVED.
"""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import AuditEvent, Incident, utc_now
from backend.app.incidents.service import IncidentService
from backend.app.schemas.postmortem import RecoveryValidationResult

DEFAULT_SERVICE_PORTS = {
    "gateway-service": 8080,
    "order-service": 8081,
    "payment-service": 8082,
    "inventory-service": 8083,
}


class RecoveryValidator:
    """Verifies that the live cluster and target service are fully operational post-remediation."""

    async def validate_recovery(
        self,
        db: AsyncSession,
        incident_id: str,
        target_service_url: Optional[str] = None,
        test_requests: int = 5,
    ) -> RecoveryValidationResult:
        """Executes live recovery verification and transitions incident to RESOLVED."""
        stmt = select(Incident).where(Incident.id == incident_id)
        res = await db.execute(stmt)
        incident = res.scalar_one_or_none()
        if not incident:
            raise ValueError(f"Incident '{incident_id}' not found.")

        if incident.status not in ("REMEDIATED", "RESOLVED"):
            raise ValueError(
                f"Cannot validate recovery: incident status must be 'REMEDIATED' (current: '{incident.status}')."
            )

        suspect = incident.suspect_service or "payment-service"
        port = DEFAULT_SERVICE_PORTS.get(suspect, 8082)
        base_url = target_service_url or f"http://127.0.0.1:{port}"

        cluster_health = {}
        succeeded = 0
        failed = 0
        errors = []

        async with httpx.AsyncClient(timeout=3.0) as client:
            # 1. Check target service /health
            try:
                h_resp = await client.get(f"{base_url}/health")
                cluster_health[suspect] = h_resp.json() if h_resp.status_code == 200 else {"status": "DEGRADED"}
            except Exception as exc:
                cluster_health[suspect] = {"status": "UNREACHABLE", "error": str(exc)}

            # 2. Replay baseline transactions
            for i in range(test_requests):
                try:
                    if "payment" in suspect:
                        req_url = f"{base_url}/payments/charge"
                        payload = {"order_id": f"recov_ord_{i}", "amount": 50.0 + i, "currency": "USD"}
                    elif "inventory" in suspect:
                        req_url = f"{base_url}/inventory/reserve"
                        payload = {"order_id": f"recov_ord_{i}", "items": [{"item_id": "item-101", "quantity": 1}]}
                    else:
                        req_url = f"{base_url}/health"
                        payload = {}

                    r = await client.post(req_url, json=payload) if payload else await client.get(req_url)
                    if r.status_code < 400:
                        succeeded += 1
                    else:
                        failed += 1
                        errors.append(f"HTTP {r.status_code}: {r.text}")
                except Exception as exc:
                    failed += 1
                    errors.append(f"Network error: {str(exc)}")

        recovery_confirmed = (failed == 0 and succeeded > 0) or (
            cluster_health.get(suspect, {}).get("status") == "UP" and failed == 0
        )
        status_str = "RESOLVED" if recovery_confirmed else "UNHEALTHY"

        if recovery_confirmed and incident.status == "REMEDIATED":
            incident.resolved_at = utc_now()
            await IncidentService.update_incident_status(
                db=db,
                incident_id=incident.id,
                new_status="RESOLVED",
                actor="RECOVERY_VALIDATOR",
                reason=f"Recovery confirmed: {succeeded}/{test_requests} baseline transactions succeeded.",
            )

        audit = AuditEvent(
            incident_id=incident.id,
            event_type="RECOVERY_VALIDATED",
            actor="RECOVERY_VALIDATOR",
            details_json=json.dumps({
                "status": status_str,
                "succeeded": succeeded,
                "failed": failed,
                "recovery_confirmed": recovery_confirmed,
                "errors": errors,
            }),
        )
        db.add(audit)
        await db.commit()
        await db.refresh(incident)

        return RecoveryValidationResult(
            incident_id=incident.id,
            status=status_str,
            cluster_health=cluster_health,
            baseline_transactions_succeeded=succeeded,
            baseline_transactions_failed=failed,
            recovery_confirmed=recovery_confirmed,
            validated_at=datetime.now(timezone.utc).isoformat(),
            details={"test_requests": test_requests, "errors": errors},
        )
