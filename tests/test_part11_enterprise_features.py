"""Test Suite for Part 11: Enterprise Production Capabilities.

Covers:
1. Enterprise Security, JWT Auth & RBAC Hierarchy
2. OpenTelemetry OTLP Standard Ingestion & Asynchronous Micro-Batching
3. Polyglot Multi-Language Remediation & Safety Verification (Python, Go, Node.js)
4. Containerized Sandbox Isolation & Graceful Host Fallback
5. Remote GitHub VCS & Slack Block Kit Dispatcher
"""

import json
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.auth import (
    DEMO_USERS,
    UserRole,
    create_jwt_token,
    verify_jwt_token,
)
from backend.app.integrations.github import github_client
from backend.app.integrations.slack import slack_dispatcher
from backend.app.main import app
from backend.app.remediation.policy_engine import PolicyEngine
from backend.app.remediation.polyglot import PolyglotEngine, SupportedLanguage
from backend.app.sandbox.container_runner import (
    ContainerSandboxRunner,
    get_default_sandbox_runner,
)
from backend.app.telemetry.otlp import parse_otlp_json
from backend.app.telemetry.queue import telemetry_buffer


@pytest.mark.asyncio
async def test_jwt_auth_lifecycle():
    """Validates JWT creation, signature verification, and login API."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Valid Login
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"username": "sre_lead", "password": "sre123"},
        )
        assert login_res.status_code == 200
        data = login_res.json()
        assert "access_token" in data
        assert data["user"]["role"] == "SRE_OPERATOR"

        token = data["access_token"]
        claims = verify_jwt_token(token)
        assert claims["sub"] == "sre_lead"
        assert claims["role"] == "SRE_OPERATOR"

        # 2. Authenticated /me endpoint
        me_res = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 200
        assert me_res.json()["username"] == "sre_lead"

        # 3. Invalid credentials rejection
        bad_res = await client.post(
            "/api/v1/auth/login",
            json={"username": "sre_lead", "password": "wrongpassword"},
        )
        assert bad_res.status_code == 401


@pytest.mark.asyncio
async def test_rbac_role_hierarchy_enforcement():
    """Verifies that low-privilege roles cannot trigger operational modifications."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Generate viewer token (DEVELOPER_VIEWER, tier 10)
        viewer_token = create_jwt_token({
            "sub": "viewer",
            "role": UserRole.DEVELOPER_VIEWER.value,
            "name": "Platform Observer",
        })

        # Try to inject chaos with viewer token -> must be 403 Forbidden
        denied_res = await client.post(
            "/api/v1/chaos/inject",
            headers={"Authorization": f"Bearer {viewer_token}"},
            json={"scenario": "LATENCY_SPIKE", "target_service": "payment-service"},
        )
        assert denied_res.status_code == 403
        assert "Access denied" in denied_res.json()["detail"]


@pytest.mark.asyncio
async def test_otlp_telemetry_standard_ingestion():
    """Verifies OpenTelemetry standard OTLP/HTTP JSON payload ingestion and buffering."""
    otlp_payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "payment-service"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
                                "spanId": "00f067aa0ba902b7",
                                "name": "HTTP POST /process-payment",
                                "startTimeUnixNano": 1700000000000000000,
                                "endTimeUnixNano": 1700000000050000000,
                                "attributes": [
                                    {"key": "http.status_code", "value": {"intValue": 500}}
                                ],
                                "status": {"code": 2, "message": "Database query timeout"},
                            }
                        ]
                    }
                ],
            }
        ]
    }

    spans = parse_otlp_json(otlp_payload)
    assert len(spans) == 1
    assert spans[0].service_name == "payment-service"
    assert spans[0].duration_ms == 50.0
    assert spans[0].status_code == "ERROR"
    assert spans[0].error_message == "Database query timeout"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Ingest via standard OTLP endpoint
        res = await client.post("/v1/traces", json=otlp_payload)
        assert res.status_code == 200
        assert "partialSuccess" in res.json()

        # Check telemetry buffer stats
        stats_res = await client.get("/v1/buffer/stats")
        assert stats_res.status_code == 200
        assert stats_res.json()["total_ingested"] >= 1


@pytest.mark.asyncio
async def test_polyglot_multi_language_safety_engine():
    """Validates AST analysis and guardrail protection across Python, Go, and Node.js."""
    # 1. Python safe vs dangerous
    safe_py = "async def query():\n    return await client.get('/items', timeout=5.0)\n"
    py_res = PolyglotEngine.evaluate_polyglot_patch(safe_py, filename="service.py")
    assert py_res.is_valid_syntax is True
    assert len(py_res.security_violations) == 0

    evil_py = "import os\ndef run(cmd):\n    eval(cmd)\n"
    evil_py_res = PolyglotEngine.evaluate_polyglot_patch(evil_py, filename="service.py")
    assert len(evil_py_res.security_violations) > 0
    assert evil_py_res.score < 1.0

    # 2. Go patch validation
    go_code = """package main
import "context"
import "time"

func HandleCheckout() {
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()
}
"""
    go_res = PolyglotEngine.evaluate_polyglot_patch(go_code, filename="handler.go")
    assert go_res.is_valid_syntax is True
    assert "Go Context with bounded deadline/timeout" in go_res.resilience_patterns_detected

    evil_go = """package main
import "unsafe"
func UnsafeHack() {
    p := unsafe.Pointer(nil)
}
"""
    evil_go_res = PolyglotEngine.evaluate_polyglot_patch(evil_go, filename="handler.go")
    assert len(evil_go_res.security_violations) > 0

    # 3. Node.js patch validation
    js_code = """const axios = require('axios');
const controller = new AbortController();
const res = await axios.get('/checkout', { timeout: 3000 });
"""
    js_res = PolyglotEngine.evaluate_polyglot_patch(js_code, filename="service.js")
    assert js_res.is_valid_syntax is True
    assert len(js_res.security_violations) == 0

    evil_js = "function dangerous() { child_process.exec(userInput); }"
    evil_js_res = PolyglotEngine.evaluate_polyglot_patch(evil_js, filename="index.js")
    assert len(evil_js_res.security_violations) > 0


@pytest.mark.asyncio
async def test_container_sandbox_runner_initialization():
    """Tests container sandbox instantiation and fallback mechanism."""
    runner = ContainerSandboxRunner(base_port=9150)
    # Check availability detection
    avail = runner.is_docker_available()
    assert isinstance(avail, bool)

    # Test factory
    default_runner = get_default_sandbox_runner()
    assert default_runner is not None


@pytest.mark.asyncio
async def test_github_and_slack_integrations():
    """Validates GitHub PR simulation and Slack Block Kit notification dispatch."""
    # 1. GitHub PR creation (simulation mode)
    pr_res = await github_client.create_pull_request(
        branch_name="traceheal/fix-test-branch",
        title="fix: resolve connection timeout",
        body="Automated verification pass",
    )
    assert pr_res["status"] in ("SIMULATED", "CREATED", "FALLBACK_SIMULATED")
    assert "pr_url" in pr_res
    assert "pr_number" in pr_res

    # 2. Slack Block Kit Alert
    slack_res = await slack_dispatcher.send_incident_alert(
        incident_id="inc_test_01",
        title="Payment Service DB Pool Saturation",
        severity="CRITICAL",
        service="payment-service",
        error_rate=0.92,
    )
    assert "dispatched" in slack_res
    assert slack_res["mode"] in ("LOCAL_SIMULATED", "REMOTE_WEBHOOK")

    # 3. REST API Integrations status
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_res = await client.get("/api/v1/integrations/status")
        assert status_res.status_code == 200
        assert "slack" in status_res.json()
        assert "github" in status_res.json()
