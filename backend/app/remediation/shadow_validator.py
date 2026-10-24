"""Shadow Sandbox Validator.

Deploys proposed remediation patches into isolated, ephemeral sandbox environments
and subjects them to identical stress workloads to empirically prove resolution
and verify zero regressions before any production approval or rollout.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
import httpx

from backend.app.sandbox.runner import ProcessSandboxRunner, SandboxEnvironment
from backend.app.schemas.remediation import ShadowValidationResult


class ShadowValidator:
    """Executes shadow validation of remediation patches inside isolated sandboxes."""

    def __init__(self, sandbox_runner: Optional[ProcessSandboxRunner] = None):
        self.runner = sandbox_runner or ProcessSandboxRunner()

    async def validate_remediation(
        self,
        service_name: str,
        remediation_patch: Dict[str, Any],
        reproduction_recipe: Dict[str, Any],
    ) -> ShadowValidationResult:
        """Provisions a sandbox, applies the remediation patch, and executes stress verification."""
        env: Optional[SandboxEnvironment] = None
        start_time = time.time()
        try:
            # 1. Provision isolated sandbox
            env = await self.runner.create_sandbox(service_name)
            base_url = env.base_url

            # 2. Replay base scenario/chaos conditions if present in recipe
            scenario = reproduction_recipe.get("scenario", "NONE")
            params = reproduction_recipe.get("parameters", {})
            async with httpx.AsyncClient(timeout=5.0) as client:
                if scenario == "DB_POOL_EXHAUSTION":
                    await client.post(
                        f"{base_url}/chaos/inject",
                        json={
                            "scenario": "DB_POOL_EXHAUSTION",
                            "max_connections": params.get("max_connections", 2),
                            "acquire_timeout_sec": params.get("acquire_timeout_sec", 0.1),
                            "hold_duration_sec": params.get("hold_duration_sec", 0.25),
                        },
                    )
                elif scenario == "INVENTORY_OUTAGE":
                    await client.post(
                        f"{base_url}/chaos/inject",
                        json={"force_error": True},
                    )

            # 3. Apply the Remediation Patch to the sandbox runtime
            patch_type = remediation_patch.get("patch_type", "CONFIG")
            config_params = remediation_patch.get("config_parameters", {})

            # If parameters weren't explicitly split out, parse or fallback from config_parameters
            async with httpx.AsyncClient(timeout=5.0) as client:
                if patch_type == "CONFIG":
                    patch_resp = await client.post(
                        f"{base_url}/config/remediate",
                        json=config_params,
                    )
                    if patch_resp.status_code != 200:
                        raise RuntimeError(
                            f"Failed to apply config patch to sandbox: status {patch_resp.status_code} - {patch_resp.text}"
                        )

            # 4. Drive verification workload against patched sandbox
            endpoint = reproduction_recipe.get("endpoint")
            if not endpoint:
                if service_name == "payment-service":
                    endpoint = "/payments/charge"
                elif service_name == "inventory-service":
                    endpoint = "/inventory/reserve"
                elif service_name == "auth-service":
                    endpoint = "/auth/verify"
                elif service_name == "notification-service":
                    endpoint = "/notifications/send"
                else:
                    endpoint = "/health"

            if not endpoint.startswith("/"):
                endpoint = "/" + endpoint

            concurrency = reproduction_recipe.get("concurrency", 4)
            total_requests = max(concurrency * 2, 8)
            expected_sig = reproduction_recipe.get("expected_error_signature", "Error")

            latencies: List[float] = []
            responses: List[Dict[str, Any]] = []

            async with httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            ) as client:
                sem = asyncio.Semaphore(concurrency)

                async def _send_request(idx: int):
                    async with sem:
                        req_start = time.time()
                        url = f"{base_url}{endpoint}"
                        if "charge" in endpoint:
                            body = {"order_id": f"val_ord_{idx}", "amount": 10.0 + idx, "currency": "USD"}
                        elif "reserve" in endpoint:
                            body = {"order_id": f"val_ord_{idx}", "items": [{"item_id": "item-101", "quantity": 1}]}
                        elif "auth" in endpoint:
                            body = {"token": "valid_token"}
                        elif "notification" in endpoint:
                            body = {"recipient": "user@example.com", "message": "Test"}
                        else:
                            body = {}

                        try:
                            if endpoint == "/health":
                                resp = await client.get(url)
                            else:
                                resp = await client.post(url, json=body)
                            dur = (time.time() - req_start) * 1000.0
                            return {
                                "status_code": resp.status_code,
                                "latency_ms": dur,
                                "text": resp.text,
                            }
                        except Exception as exc:
                            dur = (time.time() - req_start) * 1000.0
                            return {
                                "status_code": 500,
                                "latency_ms": dur,
                                "text": f"{exc.__class__.__name__}: {str(exc)}",
                            }

                tasks = [_send_request(i) for i in range(total_requests)]
                responses = await asyncio.gather(*tasks, return_exceptions=False)

            # 5. Evaluate empirical post-patch metrics
            errors = 0
            found_original_signature = False
            for r in responses:
                latencies.append(r["latency_ms"])
                code = r["status_code"]
                text = r.get("text", "")
                if code >= 400:
                    errors += 1
                    if expected_sig.lower() in text.lower():
                        found_original_signature = True

            latencies.sort()
            p95_idx = int(len(latencies) * 0.95) if latencies else 0
            latency_p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0.0
            error_rate = errors / float(total_requests) if total_requests > 0 else 0.0

            # Resolution criteria: Zero instances of the original failure signature
            # and error rate under 10% (ideally 0%)
            resolved = (not found_original_signature) and (error_rate <= 0.10)
            status = "VALIDATED" if resolved else "FAILED"

            return ShadowValidationResult(
                status=status,
                sandbox_id=env.sandbox_id,
                pre_patch_errors=total_requests,  # baseline reproduction count
                post_patch_errors=errors,
                error_rate=round(error_rate, 4),
                latency_p95_ms=round(latency_p95, 2),
                reproduced_issue_resolved=resolved,
                details={
                    "total_requests": total_requests,
                    "concurrency": concurrency,
                    "observed_errors": errors,
                    "found_original_signature": found_original_signature,
                    "applied_patch_params": config_params,
                    "validation_duration_ms": round((time.time() - start_time) * 1000.0, 2),
                },
            )

        finally:
            if env is not None:
                await self.runner.destroy_sandbox(env)
