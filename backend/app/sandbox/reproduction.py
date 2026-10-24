"""Sandbox Reproduction Executor.

Replays synthetic workloads and failure configurations against isolated sandbox environments
to empirically prove or disprove root cause hypotheses.
"""

import asyncio
import time
from typing import Any, Dict, List
import httpx

from backend.app.sandbox.runner import SandboxEnvironment, SandboxExecutionResult


class ReproductionExecutor:
    """Replays reproduction recipes against isolated sandboxes."""

    async def execute_recipe(
        self,
        env: SandboxEnvironment,
        recipe: Dict[str, Any],
    ) -> SandboxExecutionResult:
        """Executes a reproduction recipe and evaluates whether the failure signature reproduces."""
        start_time = time.time()
        scenario = recipe.get("scenario", "NONE")
        endpoint = recipe.get("endpoint", "/health")
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint

        concurrency = recipe.get("concurrency")
        if not concurrency:
            concurrency = 8 if scenario == "DB_POOL_EXHAUSTION" else 1
        params = recipe.get("parameters", {})
        expected_sig = recipe.get("expected_error_signature", "Error")

        base_url = env.base_url

        # 1. Apply scenario configuration if applicable
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

        # 2. Replay synthetic load against sandbox endpoint
        responses: List[Dict[str, Any]] = []
        async with httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        ) as client:
            sem = asyncio.Semaphore(concurrency)

            async def _send_call(i: int):
                async with sem:
                    url = f"{base_url}{endpoint}"
                    if "charge" in endpoint:
                        body = {"order_id": f"sbx_ord_{i}", "amount": 25.0 + i, "currency": "USD"}
                    elif "reserve" in endpoint:
                        body = {"order_id": f"sbx_ord_{i}", "items": [{"item_id": "item-101", "quantity": 1}]}
                    else:
                        body = {}

                    try:
                        resp = await client.post(url, json=body)
                        return {
                            "status_code": resp.status_code,
                            "text": resp.text,
                        }
                    except Exception as exc:
                        return {
                            "status_code": 500,
                            "text": f"{exc.__class__.__name__}: {str(exc)}",
                        }

            tasks = [_send_call(i) for i in range(max(concurrency, 1))]
            responses = await asyncio.gather(*tasks, return_exceptions=False)

        duration_ms = (time.time() - start_time) * 1000.0

        # 3. Evaluate results against expected error signature
        reproduced = False
        observed_signature = None
        error_count = 0

        for r in responses:
            text = r.get("text", "")
            code = r.get("status_code", 200)
            if code >= 400:
                error_count += 1
                if expected_sig.lower() in text.lower():
                    reproduced = True
                    observed_signature = text[:256]

        if not observed_signature and error_count > 0:
            observed_signature = responses[0].get("text", "")[:256]

        details = {
            "scenario": scenario,
            "concurrency": concurrency,
            "total_calls": len(responses),
            "error_calls": error_count,
            "expected_signature": expected_sig,
            "responses_sample": responses[:3],
        }

        return SandboxExecutionResult(
            sandbox_id=env.sandbox_id,
            exit_code=0 if not reproduced else 500,
            stdout="",
            stderr="",
            observed_signature=observed_signature,
            reproduction_verified=reproduced,
            duration_ms=round(duration_ms, 2),
            details=details,
        )
