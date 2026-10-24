"""Test suite for Part 3: Telemetry Ingestion Pipeline, Trace DAG Builder,

Causal Failure Origin Analysis, and Service Dependency Graph.
"""

import json
import os
import sys
import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.db.session import init_db, close_db, engine, Base, async_session_factory
from backend.app.main import app
from backend.app.schemas.telemetry import SpanCreate
from backend.app.telemetry.critical_path import identify_failure_origin, identify_latency_bottleneck
from backend.app.telemetry.ingestion import ingest_spans, get_spans_by_trace
from backend.app.telemetry.service_graph import build_service_dependency_graph
from backend.app.telemetry.trace_graph import build_trace_tree


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Sets up the database schema before each test and drops tables after."""
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_trace_dag_reconstruction_and_self_time():
    """Tests building a hierarchical DAG from flat spans and calculating self-durations."""
    trace_id = "trace_dag_test_1001"

    spans = [
        # Root: Gateway
        {
            "trace_id": trace_id,
            "span_id": "span_gw_01",
            "parent_span_id": None,
            "service_name": "gateway-service",
            "operation_name": "POST /checkout",
            "start_time_ns": 1000000,
            "end_time_ns": 351000000,
            "duration_ms": 350.0,
            "status_code": "OK",
            "http_status_code": 200,
        },
        # Child 1: Order
        {
            "trace_id": trace_id,
            "span_id": "span_ord_02",
            "parent_span_id": "span_gw_01",
            "service_name": "order-service",
            "operation_name": "POST /orders/process",
            "start_time_ns": 10000000,
            "end_time_ns": 330000000,
            "duration_ms": 320.0,
            "status_code": "OK",
            "http_status_code": 200,
        },
        # Child 1.1: Inventory
        {
            "trace_id": trace_id,
            "span_id": "span_inv_03",
            "parent_span_id": "span_ord_02",
            "service_name": "inventory-service",
            "operation_name": "POST /inventory/reserve",
            "start_time_ns": 15000000,
            "end_time_ns": 55000000,
            "duration_ms": 40.0,
            "status_code": "OK",
            "http_status_code": 200,
        },
        # Child 1.2: Payment
        {
            "trace_id": trace_id,
            "span_id": "span_pay_04",
            "parent_span_id": "span_ord_02",
            "service_name": "payment-service",
            "operation_name": "POST /payments/charge",
            "start_time_ns": 60000000,
            "end_time_ns": 300000000,
            "duration_ms": 240.0,
            "status_code": "OK",
            "http_status_code": 200,
        },
    ]

    roots = build_trace_tree(spans)
    assert len(roots) == 1
    root = roots[0]

    # Verify Gateway root
    assert root.span["span_id"] == "span_gw_01"
    assert root.depth == 0
    assert root.self_duration_ms == 30.0  # 350 - 320 = 30ms
    assert len(root.children) == 1

    # Verify Order child
    order_node = root.children[0]
    assert order_node.span["span_id"] == "span_ord_02"
    assert order_node.depth == 1
    assert order_node.self_duration_ms == 40.0  # 320 - (40 + 240) = 40ms
    assert len(order_node.children) == 2

    # Verify Inventory and Payment leaf nodes
    inv_node = order_node.children[0]
    pay_node = order_node.children[1]
    assert inv_node.depth == 2
    assert inv_node.self_duration_ms == 40.0
    assert pay_node.depth == 2
    assert pay_node.self_duration_ms == 240.0

    # Serialization test
    tree_dict = root.to_dict()
    assert tree_dict["service_name"] == "gateway-service"
    assert len(tree_dict["children"]) == 1
    assert tree_dict["children"][0]["service_name"] == "order-service"


@pytest.mark.asyncio
async def test_failure_origin_pinpointing():
    """Verifies that failure origin analysis correctly isolates the root-cause service

    (payment-service with DB pool exhaustion) rather than upstream cascade proxies (502s).
    """
    trace_id = "trace_fail_origin_2002"

    spans = [
        # Gateway returns 502 because order failed
        {
            "trace_id": trace_id,
            "span_id": "span_gw_err",
            "parent_span_id": None,
            "service_name": "gateway-service",
            "operation_name": "POST /checkout",
            "duration_ms": 210.0,
            "status_code": "ERROR",
            "http_status_code": 502,
            "error_message": "GatewayCheckoutFailed: downstream returned 502",
        },
        # Order returns 502 because payment failed
        {
            "trace_id": trace_id,
            "span_id": "span_ord_err",
            "parent_span_id": "span_gw_err",
            "service_name": "order-service",
            "operation_name": "POST /orders/process",
            "duration_ms": 200.0,
            "status_code": "ERROR",
            "http_status_code": 502,
            "error_message": "OrderFailed: downstream payment service returned 500",
        },
        # Inventory succeeded
        {
            "trace_id": trace_id,
            "span_id": "span_inv_ok",
            "parent_span_id": "span_ord_err",
            "service_name": "inventory-service",
            "operation_name": "POST /inventory/reserve",
            "duration_ms": 25.0,
            "status_code": "OK",
            "http_status_code": 200,
        },
        # Payment is the root cause failure origin
        {
            "trace_id": trace_id,
            "span_id": "span_pay_root_cause",
            "parent_span_id": "span_ord_err",
            "service_name": "payment-service",
            "operation_name": "POST /payments/charge",
            "duration_ms": 170.0,
            "status_code": "ERROR",
            "http_status_code": 500,
            "error_message": "DBPoolExhaustionError: Timeout acquiring connection from database pool within 200ms",
            "attributes_json": json.dumps({"db.pool.exhausted": True, "db.pool.max_size": 2}),
        },
    ]

    report = identify_failure_origin(spans)
    assert report.has_error is True
    assert report.origin_span_id == "span_pay_root_cause"
    assert report.service_name == "payment-service"
    assert report.http_status_code == 500
    assert "DBPoolExhaustionError" in report.error_message
    assert report.depth == 2
    assert report.error_chain == ["gateway-service", "order-service", "payment-service"]
    assert report.attributes.get("db.pool.exhausted") is True


@pytest.mark.asyncio
async def test_latency_bottleneck_detection():
    """Tests identifying the span responsible for highest self-time in a trace."""
    spans = [
        {"span_id": "s1", "parent_span_id": None, "service_name": "gw", "duration_ms": 500.0},
        {"span_id": "s2", "parent_span_id": "s1", "service_name": "ord", "duration_ms": 480.0},
        {"span_id": "s3", "parent_span_id": "s2", "service_name": "db_heavy", "duration_ms": 450.0},
    ]

    bottleneck = identify_latency_bottleneck(spans)
    assert bottleneck["bottleneck_span_id"] == "s3"
    assert bottleneck["service_name"] == "db_heavy"
    assert bottleneck["self_duration_ms"] == 450.0


@pytest.mark.asyncio
async def test_service_dependency_graph_topology():
    """Tests inferring directed service dependencies and edge health metrics."""
    spans = [
        # Call 1: gw -> ord -> pay
        {"span_id": "1", "parent_span_id": None, "service_name": "gw", "status_code": "OK", "duration_ms": 100},
        {"span_id": "2", "parent_span_id": "1", "service_name": "ord", "status_code": "OK", "duration_ms": 80},
        {"span_id": "3", "parent_span_id": "2", "service_name": "pay", "status_code": "OK", "duration_ms": 50},
        # Call 2: gw -> ord -> pay (with pay error)
        {"span_id": "4", "parent_span_id": None, "service_name": "gw", "status_code": "ERROR", "duration_ms": 100},
        {"span_id": "5", "parent_span_id": "4", "service_name": "ord", "status_code": "ERROR", "duration_ms": 80},
        {"span_id": "6", "parent_span_id": "5", "service_name": "pay", "status_code": "ERROR", "duration_ms": 50},
    ]

    graph = build_service_dependency_graph(spans)
    assert len(graph["nodes"]) == 3
    assert len(graph["edges"]) == 2

    edge_map = {(e["source"], e["target"]): e for e in graph["edges"]}
    assert ("gw", "ord") in edge_map
    assert ("ord", "pay") in edge_map

    ord_pay_edge = edge_map[("ord", "pay")]
    assert ord_pay_edge["call_count"] == 2
    assert ord_pay_edge["error_count"] == 1
    assert ord_pay_edge["error_rate"] == 0.5


@pytest.mark.asyncio
async def test_telemetry_rest_api_endpoints():
    """Tests complete REST API integration via httpx ASGITransport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        h_resp = await client.get("/health")
        assert h_resp.status_code == 200
        assert h_resp.json()["status"] == "UP"

        # 2. Ingest Spans
        test_trace = "api_test_trace_3003"
        payload = [
            {
                "trace_id": test_trace,
                "span_id": "api_s1",
                "parent_span_id": None,
                "service_name": "gateway-service",
                "operation_name": "POST /api/v1/orders/checkout",
                "start_time_ns": 1700000000000,
                "end_time_ns": 1700000100000,
                "duration_ms": 100.0,
                "status_code": "OK",
                "http_status_code": 200,
            },
            {
                "trace_id": test_trace,
                "span_id": "api_s2",
                "parent_span_id": "api_s1",
                "service_name": "order-service",
                "operation_name": "POST /orders/process",
                "start_time_ns": 1700000010000,
                "end_time_ns": 1700000090000,
                "duration_ms": 80.0,
                "status_code": "OK",
                "http_status_code": 200,
            },
        ]
        ingest_resp = await client.post("/api/v1/telemetry/spans", json=payload)
        assert ingest_resp.status_code == 201
        assert ingest_resp.json()["ingested_count"] == 2

        # 3. Retrieve raw spans
        spans_resp = await client.get(f"/api/v1/telemetry/spans/{test_trace}")
        assert spans_resp.status_code == 200
        assert len(spans_resp.json()) == 2

        # 4. Retrieve DAG tree
        tree_resp = await client.get(f"/api/v1/telemetry/traces/{test_trace}/tree")
        assert tree_resp.status_code == 200
        tree_data = tree_resp.json()
        assert tree_data["trace_id"] == test_trace
        assert len(tree_data["tree"]) == 1
        assert tree_data["tree"][0]["service_name"] == "gateway-service"

        # 5. List traces
        traces_resp = await client.get("/api/v1/telemetry/traces")
        assert traces_resp.status_code == 200
        assert test_trace in traces_resp.json()["traces"]

        # 6. Retrieve service topology
        topo_resp = await client.get("/api/v1/telemetry/topology")
        assert topo_resp.status_code == 200
        topo_data = topo_resp.json()
        assert len(topo_data["nodes"]) >= 2
        assert len(topo_data["edges"]) >= 1
