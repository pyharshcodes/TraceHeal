"""Infers service dependency topology and aggregated health metrics from spans."""

from collections import defaultdict
from typing import Any, Dict, List
from backend.app.telemetry.trace_graph import normalize_span


def build_service_dependency_graph(spans: List[Any]) -> Dict[str, Any]:
    """Infers directed service call graphs and edge metrics from distributed spans."""
    if not spans:
        return {"nodes": [], "edges": []}

    normalized = [normalize_span(s) for s in spans]
    spans_by_id = {s["span_id"]: s for s in normalized if s.get("span_id")}

    # Node stats: service_name -> {spans, errors, total_duration}
    node_stats = defaultdict(lambda: {"total_spans": 0, "error_count": 0, "total_duration": 0.0})

    # Edge stats: (source, target) -> {calls, errors, total_duration}
    edge_stats = defaultdict(lambda: {"call_count": 0, "error_count": 0, "total_duration": 0.0})

    for s in normalized:
        svc = s.get("service_name") or "unknown"
        is_err = s.get("status_code") == "ERROR" or (s.get("http_status_code") or 0) >= 400
        dur = s.get("duration_ms", 0.0)

        node_stats[svc]["total_spans"] += 1
        if is_err:
            node_stats[svc]["error_count"] += 1
        node_stats[svc]["total_duration"] += dur

        parent_id = s.get("parent_span_id")
        if parent_id and parent_id in spans_by_id:
            parent_svc = spans_by_id[parent_id].get("service_name")
            if parent_svc and parent_svc != svc:
                # Inter-service edge
                edge_key = (parent_svc, svc)
                edge_stats[edge_key]["call_count"] += 1
                if is_err:
                    edge_stats[edge_key]["error_count"] += 1
                edge_stats[edge_key]["total_duration"] += dur

    # Build node list
    nodes = []
    for svc, stats in sorted(node_stats.items()):
        total = stats["total_spans"]
        errors = stats["error_count"]
        error_rate = (errors / total) if total > 0 else 0.0
        avg_dur = (stats["total_duration"] / total) if total > 0 else 0.0

        if error_rate >= 0.3:
            health = "CRITICAL"
        elif error_rate > 0.05:
            health = "DEGRADED"
        else:
            health = "HEALTHY"

        nodes.append({
            "id": svc,
            "service_name": svc,
            "total_spans": total,
            "error_count": errors,
            "error_rate": round(error_rate, 4),
            "avg_duration_ms": round(avg_dur, 2),
            "health_status": health,
        })

    # Build edge list
    edges = []
    for (src, tgt), stats in sorted(edge_stats.items()):
        calls = stats["call_count"]
        errors = stats["error_count"]
        error_rate = (errors / calls) if calls > 0 else 0.0
        avg_dur = (stats["total_duration"] / calls) if calls > 0 else 0.0

        edges.append({
            "source": src,
            "target": tgt,
            "call_count": calls,
            "error_count": errors,
            "error_rate": round(error_rate, 4),
            "avg_duration_ms": round(avg_dur, 2),
        })

    return {
        "nodes": nodes,
        "edges": edges,
    }
