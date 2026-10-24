"""Reconstructs distributed trace DAG call hierarchies from flat spans."""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class SpanNode:
    """Represents a node in the distributed call tree."""
    span: Dict[str, Any]
    children: List["SpanNode"] = field(default_factory=list)
    depth: int = 0
    self_duration_ms: float = 0.0
    is_failure_origin: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Recursively serializes node and children to dictionary."""
        return {
            "span_id": self.span.get("span_id"),
            "parent_span_id": self.span.get("parent_span_id"),
            "trace_id": self.span.get("trace_id"),
            "service_name": self.span.get("service_name"),
            "operation_name": self.span.get("operation_name"),
            "duration_ms": self.span.get("duration_ms", 0.0),
            "self_duration_ms": round(self.self_duration_ms, 2),
            "status_code": self.span.get("status_code", "UNSET"),
            "http_status_code": self.span.get("http_status_code"),
            "error_message": self.span.get("error_message"),
            "attributes": json.loads(self.span.get("attributes_json") or "{}")
            if isinstance(self.span.get("attributes_json"), str)
            else self.span.get("attributes_json") or {},
            "depth": self.depth,
            "is_failure_origin": self.is_failure_origin,
            "children": [child.to_dict() for child in self.children],
        }


def normalize_span(span: Any) -> Dict[str, Any]:
    """Normalizes TelemetrySpan ORM model, Pydantic model, or dict into a standard dict."""
    if isinstance(span, dict):
        return dict(span)
    # SQLAlchemy model or Pydantic model
    return {
        "span_id": getattr(span, "span_id", None),
        "parent_span_id": getattr(span, "parent_span_id", None),
        "trace_id": getattr(span, "trace_id", None),
        "service_name": getattr(span, "service_name", None),
        "operation_name": getattr(span, "operation_name", None),
        "start_time_ns": getattr(span, "start_time_ns", 0),
        "end_time_ns": getattr(span, "end_time_ns", 0),
        "duration_ms": getattr(span, "duration_ms", 0.0),
        "status_code": getattr(span, "status_code", "UNSET"),
        "http_status_code": getattr(span, "http_status_code", None),
        "error_message": getattr(span, "error_message", None),
        "attributes_json": getattr(span, "attributes_json", "{}"),
        "events_json": getattr(span, "events_json", "[]"),
    }


def build_trace_tree(spans: List[Any]) -> List[SpanNode]:
    """Reconstructs the hierarchical call tree for a collection of spans belonging to a trace.

    Returns a list of root SpanNodes (usually 1, or multiple if detached root spans exist).
    """
    if not spans:
        return []

    normalized = [normalize_span(s) for s in spans]
    spans_by_id: Dict[str, Dict[str, Any]] = {s["span_id"]: s for s in normalized if s.get("span_id")}
    children_map: Dict[str, List[Dict[str, Any]]] = {}

    root_candidates: List[Dict[str, Any]] = []

    for s in normalized:
        parent_id = s.get("parent_span_id")
        if not parent_id or parent_id not in spans_by_id:
            root_candidates.append(s)
        else:
            children_map.setdefault(parent_id, []).append(s)

    # Sort roots by start time
    root_candidates.sort(key=lambda x: x.get("start_time_ns", 0))

    def _build_subtree(span_data: Dict[str, Any], depth: int, visited: Set[str]) -> SpanNode:
        span_id = span_data.get("span_id")
        node = SpanNode(span=span_data, depth=depth)

        if span_id in visited:
            return node  # Break cyclic references defensively
        visited.add(span_id)

        raw_children = children_map.get(span_id, [])
        # Sort children by start time
        raw_children.sort(key=lambda x: x.get("start_time_ns", 0))

        child_nodes = []
        child_total_duration = 0.0
        for child_data in raw_children:
            child_node = _build_subtree(child_data, depth + 1, visited)
            child_nodes.append(child_node)
            child_total_duration += child_node.span.get("duration_ms", 0.0)

        node.children = child_nodes
        total_duration = span_data.get("duration_ms", 0.0)
        node.self_duration_ms = max(0.0, total_duration - child_total_duration)
        return node

    roots: List[SpanNode] = []
    visited_global: Set[str] = set()
    for root_data in root_candidates:
        roots.append(_build_subtree(root_data, depth=0, visited=visited_global))

    return roots
