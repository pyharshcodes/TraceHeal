"""Part 9 Integration Suite: Real-Time Visual SRE Command Center & Frontend UI.

Verifies:
1. Single-Page Application (SPA) HTML delivery at `/` and `/ui`.
2. Static asset resolution (CSS styling, Topology SVG renderer, Application Controller JS).
3. Chaos and cluster control endpoints (`/api/v1/chaos/status`, `/api/v1/chaos/inject`, `/api/v1/chaos/reset`).
4. Autonomous incident simulation endpoint (`/api/v1/chaos/simulate-incident`).
5. Real-time UI data contract verification across incidents, stream, and postmortems.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.db.session import async_session_factory, init_db
from backend.app.main import app


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_test_db():
    """Initializes the database schema for the test suite."""
    await init_db()
    yield


@pytest.mark.asyncio
async def test_serve_index_html_root():
    """Verifies that the root path `/` serves the SRE Command Center SPA with essential elements."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        html = resp.text

        # Validate essential UI components are present in DOM
        assert "TraceHeal" in html
        assert "SRE Command Center" in html
        assert "topologyCanvas" in html
        assert "lifecycleStepper" in html
        assert "terminalBody" in html
        assert "diffViewerCard" in html
        assert "postmortemModal" in html
        assert "btnSimulateIncident" in html
        assert "btnTriggerRca" in html


@pytest.mark.asyncio
async def test_serve_ui_alias():
    """Verifies that `/ui` serves the same Command Center SPA."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/ui")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "TraceHeal" in resp.text


@pytest.mark.asyncio
async def test_serve_static_assets():
    """Verifies static asset hosting for CSS and JS bundles."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Stylesheet
        css_resp = await client.get("/static/css/style.css")
        assert css_resp.status_code == 200
        assert "text/css" in css_resp.headers["content-type"]
        assert "--bg-root" in css_resp.text

        # 2. Main App JS Controller
        app_js_resp = await client.get("/static/js/app.js")
        assert app_js_resp.status_code == 200
        assert "javascript" in app_js_resp.headers["content-type"]
        assert "AppState" in app_js_resp.text

        # 3. Topology SVG Renderer JS
        topo_js_resp = await client.get("/static/js/topology.js")
        assert topo_js_resp.status_code == 200
        assert "javascript" in topo_js_resp.headers["content-type"]
        assert "TopologyRenderer" in topo_js_resp.text


@pytest.mark.asyncio
async def test_chaos_cluster_status():
    """Verifies querying cluster health from the SRE Command Center."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/chaos/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "cluster_connected" in data
        assert "services" in data
        assert "gateway-service" in data["services"]
        assert "payment-service" in data["services"]


@pytest.mark.asyncio
async def test_chaos_injection_and_reset():
    """Verifies injecting and resetting chaos scenarios via the Command Center API."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Inject Latency Spike
        inject_resp = await client.post(
            "/api/v1/chaos/inject",
            json={
                "scenario": "LATENCY_SPIKE",
                "target_service": "payment-service",
                "params": {"latency_sec": 2.5},
            },
        )
        assert inject_resp.status_code == 200
        inject_data = inject_resp.json()
        assert inject_data["status"] in ["INJECTED", "SIMULATED"]
        assert inject_data["target_service"] == "payment-service"

        # 2. Reset Chaos
        reset_resp = await client.post("/api/v1/chaos/reset")
        assert reset_resp.status_code == 200
        reset_data = reset_resp.json()
        assert reset_data["status"] in ["RESET_SUCCESS", "RESET_SIMULATED"]


@pytest.mark.asyncio
async def test_simulate_incident_e2e_ui_flow():
    """Verifies that the Command Center's one-click incident simulation triggers autonomous detection,

    creates an incident record, and can be retrieved by the UI.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sim_resp = await client.post(
            "/api/v1/chaos/simulate-incident",
            json={
                "fault_type": "DB_POOL_EXHAUSTION",
                "target_service": "payment-service",
                "trace_count": 3,
            },
        )
        assert sim_resp.status_code == 200
        sim_data = sim_resp.json()
        assert sim_data["status"] == "INCIDENT_SIMULATED"
        assert len(sim_data["traces_generated"]) == 3

        incident = sim_data["incident"]
        assert incident is not None
        inc_id = incident["id"]
        assert incident["suspect_service"] == "payment-service"

        # Verify incident appears in incident list used by UI
        list_resp = await client.get("/api/v1/incidents/")
        assert list_resp.status_code == 200
        incidents = list_resp.json()
        found = any(i["id"] == inc_id for i in incidents)
        assert found, f"Simulated incident {inc_id} not found in /api/v1/incidents/"

        # Verify incident transitions through lifecycle states as executed by UI action buttons
        # DETECTED -> INVESTIGATING
        patch_resp = await client.patch(
            f"/api/v1/incidents/{inc_id}/status",
            json={"status": "INVESTIGATING", "reason": "Autonomous RCA initiated by SRE"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "INVESTIGATING"

        # INVESTIGATING -> REPRODUCING
        patch_resp = await client.patch(
            f"/api/v1/incidents/{inc_id}/status",
            json={"status": "REPRODUCING", "reason": "Sandbox reproduction running"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "REPRODUCING"
