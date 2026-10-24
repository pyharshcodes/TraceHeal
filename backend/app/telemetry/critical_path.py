"""Critical path and causal failure origin analysis for distributed traces."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from backend.app.telemetry.trace_graph import SpanNode, build_trace_tree, normalize_span


@dataclass
class FailureOriginReport:
    """Detailed causal analysis report identifying where a failure originated."""
    has_error: bool
    origin_span_id: Optional[str] = None
    service_name: Optional[str] = None
    operation_name: Optional[str] = None
    http_status_code: Optional[int] = None
    error_message: Optional[str] = None
    depth: int = 0
    error_chain: List[str] = None
    attributes: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_error": self.has_error,
            "origin_span_id": self.origin_span_id,
            "service_name": self.service_name,
            "operation_name": self.operation_name,
            "http_status_code": self.http_status_code,
            "error_message": self.error_message,
            "depth": self.depth,
            "error_chain": self.error_chain or [],
            "attributes": self.attributes or {},
        }


def is_error_span(span_data: Dict[str, Any]) -> bool:
    """Determines if a span represents a failure."""
    status_code = span_data.get("status_code", "UNSET")
    http_status = span_data.get("http_status_code")
    error_msg = span_data.get("error_message")

    if status_code == "ERROR":
        return True
    if http_status and http_status >= 400:
        return True
    if error_msg:
        return True
    return False


def identify_failure_origin(spans: List[Any]) -> FailureOriginReport:
    """Finds the deepest causal origin of failure in a distributed trace.

    Distinguishes between downstream root cause errors (e.g. Database connection pool exhaustion)
    and upstream cascade proxy errors (e.g. 502 Bad Gateway).
    """
    if not spans:
        return FailureOriginReport(has_error=False)

    roots = build_trace_tree(spans)
    if not roots:
        return FailureOriginReport(has_error=False)

    best_candidate: Optional[SpanNode] = None
    best_depth: int = -1
    best_chain: List[str] = []

    def _dfs_search(node: SpanNode, current_chain: List[str]):
        nonlocal best_candidate, best_depth, best_chain

        node_is_err = is_error_span(node.span)
        svc_name = node.span.get("service_name", "unknown")

        chain = current_chain + [svc_name] if node_is_err else current_chain

        if node_is_err:
            # Check if this node is deeper than previously known failure candidate
            if node.depth > best_depth:
                best_depth = node.depth
                best_candidate = node
                best_chain = list(chain)

        # Recurse into children
        for child in node.children:
            _dfs_search(child, chain if node_is_err else [])

    for root in roots:
        _dfs_search(root, [])

    if not best_candidate:
        return FailureOriginReport(has_error=False)

    best_candidate.is_failure_origin = True
    span = best_candidate.span

    raw_attrs = span.get("attributes_json", "{}")
    attrs = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs or {}

    return FailureOriginReport(
        has_error=True,
        origin_span_id=span.get("span_id"),
        service_name=span.get("service_name"),
        operation_name=span.get("operation_name"),
        http_status_code=span.get("http_status_code"),
        error_message=span.get("error_message"),
        depth=best_candidate.depth,
        error_chain=best_chain,
        attributes=attrs,
    )


def identify_latency_bottleneck(spans: List[Any]) -> Dict[str, Any]:
    """Identifies the span with the highest self-duration (exclusive execution time)."""
    if not spans:
        return {"bottleneck_span_id": None, "service_name": None, "self_duration_ms": 0.0}

    roots = build_trace_tree(spans)
    max_node: Optional[SpanNode] = None
    max_self_duration: float = -1.0

    def _traverse(node: SpanNode):
        nonlocal max_node, max_self_duration
        if node.self_duration_ms > max_self_duration:
            max_self_duration = node.self_duration_ms
            max_node = node
        for child in node.children:
            _traverse(child)

    for root in roots:
        _traverse(root)

    if not max_node:
        return {"bottleneck_span_id": None, "service_name": None, "self_duration_ms": 0.0}

    span = max_node.span
    return {
        "bottleneck_span_id": span.get("span_id"),
        "service_name": span.get("service_name"),
        "operation_name": span.get("operation_name"),
        "self_duration_ms": round(max_node.self_duration_ms, 2),
        "total_duration_ms": round(span.get("duration_ms", 0.0), 2),
    }
