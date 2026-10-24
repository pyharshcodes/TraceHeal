"""Asynchronous High-Throughput Telemetry Ingestion Buffer.

Provides non-blocking micro-batching for high-volume OpenTelemetry distributed traces.
Reduces database lock contention by flushing spans in batched transactions.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import logger
from backend.app.db.session import AsyncSessionLocal
from backend.app.schemas.telemetry import SpanCreate
from backend.app.telemetry.ingestion import ingest_spans


class AsyncTelemetryBuffer:
    """In-memory bounded asynchronous queue with micro-batch flushing."""

    def __init__(self, maxsize: int = 10000, batch_size: int = 100, flush_interval_secs: float = 0.2):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.batch_size = batch_size
        self.flush_interval_secs = flush_interval_secs
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self.total_ingested = 0
        self.total_flushed = 0
        self.total_dropped = 0
        self.batch_count = 0

    async def start(self):
        """Starts the background batch flusher task."""
        if not self._running:
            self._running = True
            self._worker_task = asyncio.create_task(self._flush_loop())
            logger.info("Telemetry ingestion buffer worker started.")

    async def stop(self):
        """Stops the worker and flushes any pending spans."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        await self.flush_now()
        logger.info(f"Telemetry buffer stopped. Ingested: {self.total_ingested}, Flushed: {self.total_flushed}")

    async def push(self, span: SpanCreate) -> bool:
        """Enqueues a span non-blockingly. Drops if queue is full."""
        try:
            self.queue.put_nowait(span)
            self.total_ingested += 1
            return True
        except asyncio.QueueFull:
            self.total_dropped += 1
            logger.warning("Telemetry buffer full! Dropping span to prevent memory bloat.")
            return False

    async def push_batch(self, spans: List[SpanCreate]) -> int:
        """Enqueues multiple spans."""
        enqueued = 0
        for s in spans:
            if await self.push(s):
                enqueued += 1
        return enqueued

    async def flush_now(self) -> int:
        """Drains the current queue and persists immediately to database."""
        batch: List[SpanCreate] = []
        while not self.queue.empty() and len(batch) < 500:
            try:
                batch.append(self.queue.get_nowait())
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

        if not batch:
            return 0

        async with AsyncSessionLocal() as session:
            try:
                await ingest_spans(session, batch)
                self.total_flushed += len(batch)
                self.batch_count += 1
                return len(batch)
            except Exception as err:
                logger.error(f"Failed to persist span batch: {err}")
                return 0

    async def _flush_loop(self):
        """Continuous micro-batch flushing loop."""
        while self._running:
            try:
                await asyncio.sleep(self.flush_interval_secs)
                if not self.queue.empty():
                    await self.flush_now()
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error(f"Error in telemetry buffer worker loop: {err}")

    def get_stats(self) -> Dict[str, Any]:
        """Returns operational metrics for telemetry buffer."""
        return {
            "queue_depth": self.queue.qsize(),
            "total_ingested": self.total_ingested,
            "total_flushed": self.total_flushed,
            "total_dropped": self.total_dropped,
            "batches_committed": self.batch_count,
            "worker_active": self._running,
        }


# Global singleton instance
telemetry_buffer = AsyncTelemetryBuffer()
