"""OpenTelemetry and W3C Trace Context integration for target microservices.

Implements W3C Trace Context recommendation (RFC traceparent format)
with in-memory span buffering and optional TraceHeal backend forwarding.
"""

import contextvars
import json
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variables for distributed propagation within the current coroutine context
ctx_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("ctx_trace_id", default=None)
ctx_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("ctx_span_id", default=None)


def generate_trace_id() -> str:
    """Generates a standard 32-hex-character (16-byte) W3C trace ID."""
    return secrets.token_hex(16)


def generate_span_id() -> str:
    """Generates a standard 16-hex-character (8-byte) W3C span ID."""
    return secrets.token_hex(8)


def parse_traceparent(header: Optional[str]) -> Optional[Tuple[str, str, bool]]:
    """Parses a W3C traceparent header: 'version-trace_id-parent_id-trace_flags'.

    Returns (trace_id, parent_id, is_sampled) or None if invalid.
    """
    if not header:
        return None
    parts = header.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, parent_id, flags = parts
    if len(trace_id) != 32 or len(parent_id) != 16:
        return None
    sampled = flags == "01"
    return trace_id, parent_id, sampled


def format_traceparent(trace_id: str, span_id: str, sampled: bool = True) -> str:
    """Formats trace and span IDs into W3C traceparent string."""
    flags = "01" if sampled else "00"
    return f"00-{trace_id}-{span_id}-{flags}"


class SpanCollector:
    """Thread-safe, coroutine-safe in-memory buffer of captured spans."""
    _instance = None

    def __init__(self):
        self._spans: List[Dict[str, Any]] = []

    @classmethod
    def get_instance(cls) -> "SpanCollector":
        if cls._instance is None:
            cls._instance = SpanCollector()
        return cls._instance

    def record_span(self, span: Dict[str, Any]):
        """Records a completed span."""
        self._spans.append(span)

    def get_spans(
        self,
        trace_id: Optional[str] = None,
        service_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns filtered spans."""
        results = list(self._spans)
        if not results:
            try:
                import json
                import urllib.request
                req = urllib.request.Request("http://127.0.0.1:8080/collector/spans")
                with urllib.request.urlopen(req, timeout=0.6) as resp:
                    if resp.status == 200:
                        results = json.loads(resp.read().decode())
            except Exception:
                pass
        if trace_id:
            results = [s for s in results if s.get("trace_id") == trace_id]
        if service_name:
            results = [s for s in results if s.get("service_name") == service_name]
        return list(results)

    def clear(self):
        """Clears all stored spans."""
        self._spans.clear()
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:8080/collector/clear", method="POST")
            with urllib.request.urlopen(req, timeout=0.6):
                pass
        except Exception:
            pass

    async def flush_to_backend(self, backend_url: str = "http://127.0.0.1:8000") -> int:
        """Pushes buffered spans to TraceHeal telemetry ingestion endpoint."""
        import httpx
        if not self._spans:
            return 0
        spans_to_send = list(self._spans)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(f"{backend_url}/api/v1/telemetry/spans", json=spans_to_send)
                if resp.status_code == 201:
                    return len(spans_to_send)
                return 0
        except Exception:
            return 0


collector = SpanCollector.get_instance()


class TraceContextMiddleware:
    """Pure ASGI middleware that extracts incoming W3C traceparent,

    maintains coroutine context, records server spans, and attaches
    traceparent to outgoing HTTP response headers.
    """

    def __init__(self, app, service_name: str):
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        raw_traceparent = None
        for k, v in headers:
            if k.lower() == b"traceparent":
                raw_traceparent = v.decode("latin1", errors="ignore")
                break

        parsed = parse_traceparent(raw_traceparent)
        if parsed:
            trace_id, parent_span_id, _ = parsed
        else:
            trace_id = generate_trace_id()
            parent_span_id = None

        server_span_id = generate_span_id()

        token_trace = ctx_trace_id.set(trace_id)
        token_span = ctx_span_id.set(server_span_id)

        start_time_ns = time.time_ns()
        http_status_box = [200]
        error_message_box = [None]

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                http_status_box[0] = message.get("status", 200)
                resp_headers = list(message.get("headers", []))
                tp_val = format_traceparent(trace_id, server_span_id).encode("latin1")
                resp_headers.append((b"traceparent", tp_val))
                message["headers"] = resp_headers
            await send(message)

        method = scope.get("method", "GET")
        path = scope.get("path", "/")

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            http_status_box[0] = 500
            error_message_box[0] = str(exc)
            raise
        finally:
            end_time_ns = time.time_ns()
            duration_ms = (end_time_ns - start_time_ns) / 1_000_000.0
            http_status = http_status_box[0]
            status_code_str = "ERROR" if http_status >= 400 else "OK"

            attributes = {
                "http.method": method,
                "http.target": path,
                "service.name": self.service_name,
            }

            span_record = {
                "trace_id": trace_id,
                "span_id": server_span_id,
                "parent_span_id": parent_span_id,
                "service_name": self.service_name,
                "operation_name": f"{method} {path}",
                "start_time_ns": start_time_ns,
                "end_time_ns": end_time_ns,
                "duration_ms": duration_ms,
                "status_code": status_code_str,
                "http_status_code": http_status,
                "error_message": error_message_box[0],
                "attributes_json": json.dumps(attributes),
                "events_json": json.dumps([]),
            }
            if not path.startswith("/collector"):
                collector.record_span(span_record)

            ctx_trace_id.reset(token_trace)
            ctx_span_id.reset(token_span)
