"""Traced HTTP client for inter-service communication with automatic W3C traceparent injection."""

import asyncio
import json
import time
from typing import Any, Dict, Optional
import httpx

from target_services.tracer import (
    collector,
    ctx_span_id,
    ctx_trace_id,
    format_traceparent,
    generate_span_id,
    generate_trace_id,
)


class TracedAsyncClient:
    """HTTP client wrapper that attaches W3C traceparent headers

    and records outbound client spans to the collector.
    """

    def __init__(self, service_name: str, timeout: float = 5.0):
        self.service_name = service_name
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_client(self) -> httpx.AsyncClient:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._client is None
            or self._client.is_closed
            or getattr(self, "_client_loop", None) is not current_loop
        ):
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=2.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
            )
            self._client_loop = current_loop
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
            self._client_loop = None

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Any] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        headers = dict(headers or {})
        to = timeout or self.timeout

        # Retrieve current trace context or generate new
        trace_id = ctx_trace_id.get() or generate_trace_id()
        parent_span_id = ctx_span_id.get()
        client_span_id = generate_span_id()

        # Inject traceparent
        headers["traceparent"] = format_traceparent(trace_id, client_span_id)

        start_time_ns = time.time_ns()
        http_status = 500
        status_code_str = "OK"
        error_msg = None

        attributes = {
            "http.method": method.upper(),
            "http.url": str(url),
            "client.service": self.service_name,
        }

        client = self._get_client()
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_data,
                timeout=to,
            )
            http_status = response.status_code
            if http_status >= 500:
                status_code_str = "ERROR"
                error_msg = f"Downstream returned HTTP {http_status}: {response.text[:128]}"
            elif http_status >= 400:
                status_code_str = "ERROR"
                error_msg = f"Client error HTTP {http_status}: {response.text[:128]}"
            return response
        except Exception as exc:
            status_code_str = "ERROR"
            http_status = 504 if isinstance(exc, (httpx.TimeoutException, httpx.ReadTimeout)) else 500
            error_msg = f"{exc.__class__.__name__}: {str(exc)}"
            attributes["error.type"] = exc.__class__.__name__
            raise exc
        finally:
            end_time_ns = time.time_ns()
            duration_ms = (end_time_ns - start_time_ns) / 1_000_000.0

            span_record = {
                "trace_id": trace_id,
                "span_id": client_span_id,
                "parent_span_id": parent_span_id,
                "service_name": self.service_name,
                "operation_name": f"CALL {method.upper()} {url}",
                "start_time_ns": start_time_ns,
                "end_time_ns": end_time_ns,
                "duration_ms": duration_ms,
                "status_code": status_code_str,
                "http_status_code": http_status,
                "error_message": error_msg,
                "attributes_json": json.dumps(attributes),
                "events_json": json.dumps([]),
            }
            collector.record_span(span_record)

    async def get(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        return await self.request("POST", url, **kwargs)
