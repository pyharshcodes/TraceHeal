"""OpenTelemetry Standard OTLP/HTTP Receiver (RFC/W3C Compliant).

Exposes standard POST /v1/traces endpoint for native ingestion from OpenTelemetry
Java/Go/Python/Node SDKs, Grafana Alloy, OpenTelemetry Collector, and Envoy proxies.
"""

import json
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.db.session import get_db
from backend.app.schemas.telemetry import SpanCreate
from backend.app.telemetry.queue import telemetry_buffer

router = APIRouter(tags=["OpenTelemetry OTLP Receiver"])


def _extract_attr_val(val_dict: Any) -> Any:
    """Extracts typed value from OTLP attribute value object."""
    if not isinstance(val_dict, dict):
        return val_dict
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in val_dict:
            return val_dict[key]
    if "arrayValue" in val_dict and "values" in val_dict["arrayValue"]:
        return [_extract_attr_val(v) for v in val_dict["arrayValue"]["values"]]
    if "kvlistValue" in val_dict and "values" in val_dict["kvlistValue"]:
        return {item["key"]: _extract_attr_val(item.get("value", {})) for item in val_dict["kvlistValue"]["values"]}
    return str(val_dict)


def parse_otlp_json(payload: Dict[str, Any], default_incident_id: Optional[str] = None) -> List[SpanCreate]:
    """Parses standard OTLP/HTTP JSON payload into TraceHeal SpanCreate models."""
    parsed_spans: List[SpanCreate] = []
    resource_spans = payload.get("resourceSpans", [])

    for r_span in resource_spans:
        resource = r_span.get("resource", {})
        res_attrs: Dict[str, Any] = {}
        for attr in resource.get("attributes", []):
            k = attr.get("key", "")
            v = _extract_attr_val(attr.get("value", {}))
            res_attrs[k] = v

        service_name = res_attrs.get("service.name", "unknown-service")

        # Support scopeSpans or instrumentationLibrarySpans
        scope_spans = r_span.get("scopeSpans", []) or r_span.get("instrumentationLibrarySpans", [])
        for s_scope in scope_spans:
            for span in s_scope.get("spans", []):
                trace_id = str(span.get("traceId", ""))
                span_id = str(span.get("spanId", ""))
                parent_span_id = str(span.get("parentSpanId", "")) if span.get("parentSpanId") else None
                name = str(span.get("name", "operation"))

                try:
                    start_ns = int(span.get("startTimeUnixNano", time.time_ns()))
                    end_ns = int(span.get("endTimeUnixNano", start_ns))
                except (ValueError, TypeError):
                    start_ns = time.time_ns()
                    end_ns = start_ns

                duration_ms = max(0.01, (end_ns - start_ns) / 1_000_000.0)

                # Parse span attributes
                span_attrs: Dict[str, Any] = {}
                for attr in span.get("attributes", []):
                    k = attr.get("key", "")
                    v = _extract_attr_val(attr.get("value", {}))
                    span_attrs[k] = v

                # Merge resource attributes for context
                merged_attrs = {**res_attrs, **span_attrs}

                # Status Code parsing
                status_obj = span.get("status", {})
                code = status_obj.get("code")
                error_msg = status_obj.get("message")
                status_str = "OK"

                # In OTLP: 0 = UNSET, 1 = OK, 2 = ERROR
                if code == 2 or code == "STATUS_CODE_ERROR" or str(code).upper() == "ERROR":
                    status_str = "ERROR"
                elif code == 1 or code == "STATUS_CODE_OK":
                    status_str = "OK"
                else:
                    status_str = "UNSET"

                # Check HTTP status
                http_status = None
                for hk in ("http.status_code", "http.response.status_code"):
                    if hk in span_attrs:
                        try:
                            http_status = int(span_attrs[hk])
                            if http_status >= 400:
                                status_str = "ERROR"
                        except (ValueError, TypeError):
                            pass

                # Parse Events
                events = span.get("events", [])
                for ev in events:
                    if ev.get("name") == "exception" and not error_msg:
                        for ev_attr in ev.get("attributes", []):
                            if ev_attr.get("key") in ("exception.message", "message"):
                                error_msg = _extract_attr_val(ev_attr.get("value", {}))

                parsed_spans.append(
                    SpanCreate(
                        trace_id=trace_id,
                        span_id=span_id,
                        parent_span_id=parent_span_id,
                        service_name=service_name,
                        operation_name=name,
                        start_time_ns=start_ns,
                        end_time_ns=end_ns,
                        duration_ms=round(duration_ms, 2),
                        status_code=status_str,
                        http_status_code=http_status,
                        error_message=error_msg,
                        attributes_json=json.dumps(merged_attrs),
                        events_json=json.dumps(events) if events else None,
                        incident_id=default_incident_id,
                    )
                )

    return parsed_spans


@router.post("/v1/traces")
async def otlp_receive_traces(
    request: Request,
    x_incident_id: Optional[str] = Header(None, alias="X-Incident-ID"),
    incident_id: Optional[str] = Query(None),
):
    """Standard OpenTelemetry Protocol (OTLP/HTTP) endpoint.

    Complies with official OpenTelemetry Collector exporter specifications.
    Ingests JSON-encoded ResourceSpans asynchronously into the micro-batching buffer.
    """
    try:
        payload = await request.json()
    except Exception as err:
        logger.error(f"Failed to decode OTLP JSON payload: {err}")
        return {"partialSuccess": {"errorMessage": f"Malformed JSON: {str(err)}", "rejectedDataPoints": 0}}

    active_incident_id = x_incident_id or incident_id
    spans = parse_otlp_json(payload, default_incident_id=active_incident_id)

    if not spans:
        return {"partialSuccess": {}}

    # Push to buffer
    await telemetry_buffer.push_batch(spans)

    return {"partialSuccess": {}}


@router.get("/v1/buffer/stats")
async def get_buffer_stats():
    """Returns telemetry micro-batch buffer throughput and health metrics."""
    return telemetry_buffer.get_stats()


@router.post("/v1/buffer/flush")
async def flush_buffer_manually():
    """Forces an immediate persistence of all queued telemetry spans."""
    flushed = await telemetry_buffer.flush_now()
    return {"status": "SUCCESS", "spans_flushed": flushed}
