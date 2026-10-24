"""Autonomous Sliding-Window Anomaly Detection Daemon.

Continuously observes real-time distributed telemetry spans in a sliding window,
computes error and latency rate spikes, and automatically triggers incident
formation and autonomous agent intervention without human polling.
"""

import asyncio
import time
from typing import Any, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.session import async_session_factory
from backend.app.events.hooks import emit_incident_state_change, emit_telemetry_spike
from backend.app.incidents.detector import IncidentDetector
from backend.app.telemetry.ingestion import get_all_spans


class AnomalyDetectorDaemon:
    """Background sliding-window watcher that automatically surfaces incidents."""

    def __init__(self, check_interval_sec: float = 3.0, error_threshold: float = 0.15):
        self.check_interval_sec = check_interval_sec
        self.error_threshold = error_threshold
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._detector = IncidentDetector(error_rate_threshold=error_threshold)
        self._last_check_time: Optional[float] = None
        self._last_error_rate: float = 0.0
        self._total_scans: int = 0
        self._total_incidents_triggered: int = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "check_interval_sec": self.check_interval_sec,
            "error_threshold": self.error_threshold,
            "last_error_rate": round(self._last_error_rate, 3),
            "total_scans": self._total_scans,
            "total_incidents_triggered": self._total_incidents_triggered,
            "last_check_time": self._last_check_time,
        }

    async def start(self):
        """Starts the background anomaly observation daemon."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"[ANOMALY DAEMON] Started sliding-window watcher (interval: {self.check_interval_sec}s, threshold: {self.error_threshold * 100}%)")

    async def stop(self):
        """Stops the daemon gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[ANOMALY DAEMON] Stopped sliding-window watcher")

    async def _monitor_loop(self):
        """Periodic sliding window inspection loop."""
        while self._running:
            try:
                await self._inspect_sliding_window()
            except Exception as e:
                logger.debug(f"[ANOMALY DAEMON] Sliding window scan error: {e}")

            try:
                await asyncio.sleep(self.check_interval_sec)
            except asyncio.CancelledError:
                break

    async def _inspect_sliding_window(self):
        """Inspects the most recent 100 spans and correlates errors if rate threshold exceeded."""
        self._last_check_time = time.time()
        self._total_scans += 1

        async with async_session_factory() as session:
            spans = await get_all_spans(session, limit=100)
            if not spans:
                self._last_error_rate = 0.0
                return

            error_spans = [
                s for s in spans
                if s.status_code == "ERROR" or (s.http_status_code and s.http_status_code >= 500) or s.error_message
            ]
            error_rate = len(error_spans) / max(1, len(spans))
            self._last_error_rate = error_rate

            if error_rate >= self.error_threshold and error_spans:
                # Trigger correlation engine
                incidents = await self._detector.scan_and_correlate(session, spans)
                if incidents:
                    self._total_incidents_triggered += len(incidents)
                    for inc in incidents:
                        logger.warning(
                            f"[ANOMALY DAEMON] Auto-detected incident {inc.id} on service '{inc.suspect_service}' "
                            f"(window error rate: {error_rate * 100:.1f}%)"
                        )
                        await emit_telemetry_spike(
                            service_name=inc.suspect_service or "cluster",
                            metric="error_rate",
                            value=round(error_rate * 100, 1),
                            error_message=inc.title,
                        )
                        await emit_incident_state_change(
                            incident_id=inc.id,
                            from_status="NONE",
                            to_status=inc.status,
                            reason=f"Sliding window error rate {error_rate * 100:.1f}% exceeded threshold",
                            actor="DAEMON_AUTO_DETECTOR",
                        )


# Global singleton instance
anomaly_detector_daemon = AnomalyDetectorDaemon()
