"""Tests for Part 8: Real-Time Event Streaming, Observability & Live Agent Terminal SSE."""

import asyncio
import json
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.events.bus import EventBus, event_bus
from backend.app.events.hooks import (
    emit_agent_action,
    emit_agent_thought,
    emit_sandbox_log,
    emit_system_vital,
    emit_telemetry_spike,
)
from backend.app.events.streaming import event_stream_generator, format_sse
from backend.app.main import app
from backend.app.schemas.events import TraceHealEvent


@pytest_asyncio.fixture(autouse=True)
def reset_event_bus():
    """Resets the event bus state before each test."""
    event_bus.clear()
    yield
    event_bus.clear()


@pytest.mark.asyncio
async def test_event_bus_pub_sub_routing_and_wildcards():
    """Validates topic routing, wildcard patterns, and subscriber isolation."""
    bus = EventBus()

    # Create 3 distinct subscriber queues
    agent_sub = await bus.subscribe(topic_pattern="agent:*")
    telemetry_sub = await bus.subscribe(topic_pattern="telemetry:spike")
    global_sub = await bus.subscribe(topic_pattern="*")

    assert bus.subscriber_count == 3

    # Publish agent thought
    ev1 = TraceHealEvent(
        topic="agent:thought",
        event_type="AGENT_THINKING",
        actor="RCA_AGENT",
        message="Analyzing trace DAG for latency bottlenecks...",
    )
    # Publish telemetry spike
    ev2 = TraceHealEvent(
        topic="telemetry:spike",
        event_type="SPIKE_DETECTED",
        actor="MONITOR",
        message="500 errors exceeded 15% threshold in payment-service",
    )
    # Publish sandbox log
    ev3 = TraceHealEvent(
        topic="sandbox:stdout",
        event_type="LOG_LINE",
        actor="SANDBOX",
        message="Uvicorn running on http://127.0.0.1:9120",
    )

    await bus.publish(ev1)
    await bus.publish(ev2)
    await bus.publish(ev3)

    # 1. agent_sub should receive only ev1
    assert agent_sub.qsize() == 1
    got_agent = agent_sub.get_nowait()
    assert got_agent.id == ev1.id
    assert got_agent.topic == "agent:thought"

    # 2. telemetry_sub should receive only ev2
    assert telemetry_sub.qsize() == 1
    got_telem = telemetry_sub.get_nowait()
    assert got_telem.id == ev2.id

    # 3. global_sub should receive all 3
    assert global_sub.qsize() == 3

    # Test unsubscribe
    await bus.unsubscribe(agent_sub)
    assert bus.subscriber_count == 2


@pytest.mark.asyncio
async def test_event_bus_replay_buffer_and_incident_filter():
    """Validates ring-buffer replay on late subscription and incident-specific filtering."""
    bus = EventBus(buffer_size=10)

    # Publish events for Incident A and Incident B
    for i in range(3):
        await bus.publish(
            TraceHealEvent(
                topic="agent:thought",
                incident_id="inc_AAA",
                event_type="THOUGHT",
                message=f"Investigation step {i} for inc_AAA",
            )
        )
    for i in range(2):
        await bus.publish(
            TraceHealEvent(
                topic="agent:thought",
                incident_id="inc_BBB",
                event_type="THOUGHT",
                message=f"Investigation step {i} for inc_BBB",
            )
        )

    # Late subscriber connects with incident filter for inc_AAA and replay=10
    late_sub = await bus.subscribe(topic_pattern="*", incident_id="inc_AAA", replay_last=10)
    assert late_sub.qsize() == 3

    while not late_sub.empty():
        ev = late_sub.get_nowait()
        assert ev.incident_id == "inc_AAA"

    # Query history API
    history = bus.get_history(incident_id="inc_AAA")
    assert len(history) == 3


@pytest.mark.asyncio
async def test_agent_broadcasting_hooks():
    """Validates typed helper hooks broadcasting to the global event bus."""
    sub = await event_bus.subscribe(topic_pattern="*")

    # 1. Agent thought
    t_ev = await emit_agent_thought(
        incident_id="inc_123",
        agent_name="RCA_AGENT",
        thought="Suspect DB connection pool saturation based on 500 error code.",
        step="HYPOTHESIS_FORMATION",
    )
    assert t_ev.topic == "agent:thought"
    assert t_ev.payload["step"] == "HYPOTHESIS_FORMATION"

    # 2. Agent action
    a_ev = await emit_agent_action(
        incident_id="inc_123",
        agent_name="VERIFICATION_AGENT",
        action="Launching isolated sandbox runner on port 9108",
        details={"port": 9108},
    )
    assert a_ev.topic == "agent:action"

    # 3. Sandbox log
    s_ev = await emit_sandbox_log(
        incident_id="inc_123",
        sandbox_id="sbx_a1b2",
        stream="stdout",
        line="INFO: Application startup complete.",
    )
    assert s_ev.topic == "sandbox:stdout"

    # 4. Telemetry spike
    spk_ev = await emit_telemetry_spike(
        service_name="payment-service",
        error_rate=0.85,
        duration_ms=740.0,
        error_message="DBPoolExhaustionError: connection timeout",
        incident_id="inc_123",
    )
    assert spk_ev.topic == "telemetry:spike"

    # 5. System vital
    v_ev = await emit_system_vital(
        metric_name="cluster_active_connections",
        value=15.0,
        unit="conns",
    )
    assert v_ev.topic == "system:metric"

    # Verify all 5 arrived on subscriber queue
    assert sub.qsize() == 5
    await event_bus.unsubscribe(sub)


@pytest.mark.asyncio
async def test_sse_formatting_and_stream_generator():
    """Validates W3C SSE wire format syntax and heartbeat ping generator."""
    ev = TraceHealEvent(
        topic="agent:thought",
        incident_id="inc_888",
        event_type="THINKING",
        message="Simulating failure in sandbox",
    )

    sse_text = format_sse(ev)
    assert sse_text.startswith(f"id: {ev.id}\n")
    assert f"event: {ev.topic}\n" in sse_text
    assert f'"message":"{ev.message}"' in sse_text
    assert sse_text.endswith("\n\n")

    # Test stream generator consumption with fast heartbeat
    gen = event_stream_generator(topic="agent:*", heartbeat_sec=0.1, replay=0)

    # 1. First yield is connection greeting comment
    greeting = await anext(gen)
    assert greeting.startswith(": connected to TraceHeal")

    # 2. Publish event and verify generator yields event
    await event_bus.publish(ev)
    event_chunk = await anext(gen)
    assert f"id: {ev.id}\n" in event_chunk
    assert "agent:thought" in event_chunk

    # 3. Wait for heartbeat timeout
    ping_chunk = await anext(gen)
    assert ping_chunk == ": ping\n\n"

    # Clean close generator
    await gen.aclose()


@pytest.mark.asyncio
async def test_streaming_rest_api_lifecycle():
    """Tests the SSE endpoints and programmatic event publishing via FastAPI AsyncClient."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Publish custom event via API
        pub_resp = await client.post(
            "/api/v1/stream/publish",
            json={
                "topic": "agent:thought",
                "event_type": "USER_ACTION",
                "message": "SRE Operator requested shadow validation.",
                "incident_id": "inc_api_test",
                "actor": "UI_CLIENT",
                "payload": {"button": "verify_sandbox"},
            },
        )
        assert pub_resp.status_code == 201
        data = pub_resp.json()
        assert data["status"] == "PUBLISHED"
        assert data["topic"] == "agent:thought"
        event_id = data["event_id"]

        # 2. Query event history
        hist_resp = await client.get("/api/v1/stream/history?topic=agent:*")
        assert hist_resp.status_code == 200
        history = hist_resp.json()
        assert len(history) >= 1
        assert any(h["id"] == event_id for h in history)

        # 3. Connect to universal SSE stream
        async with client.stream("GET", "/api/v1/stream/events?replay=1&max_events=1") as stream_resp:
            assert stream_resp.status_code == 200
            assert "text/event-stream" in stream_resp.headers["content-type"]
            assert "no-cache" in stream_resp.headers["cache-control"]

            lines = []
            async for chunk in stream_resp.aiter_lines():
                if chunk:
                    lines.append(chunk)
            assert len(lines) > 0

        # 4. Connect to dedicated incident terminal SSE stream
        async with client.stream("GET", "/api/v1/stream/incidents/inc_api_test?replay=1&max_events=1") as inc_stream:
            assert inc_stream.status_code == 200
            assert "text/event-stream" in inc_stream.headers["content-type"]

            inc_lines = []
            async for chunk in inc_stream.aiter_lines():
                if chunk:
                    inc_lines.append(chunk)
            assert len(inc_lines) > 0

        # 5. Connect to metrics SSE stream
        await emit_system_vital("cluster_cpu", 42.0, "%")
        async with client.stream("GET", "/api/v1/stream/metrics?replay=1&max_events=1") as metric_stream:
            assert metric_stream.status_code == 200
            assert "text/event-stream" in metric_stream.headers["content-type"]

            m_lines = []
            async for chunk in metric_stream.aiter_lines():
                if chunk:
                    m_lines.append(chunk)
            assert len(m_lines) > 0
