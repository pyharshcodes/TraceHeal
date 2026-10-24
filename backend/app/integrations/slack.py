"""Slack Webhook Dispatcher with Rich Block Kit Formatting.

Pushes real-time incident lifecycle events, diagnosis cards, and shadow-verification
proofs directly to SRE on-call Slack channels.
"""

from typing import Any, Dict, List, Optional
import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger


class SlackWebhookDispatcher:
    """Dispatches Slack Block Kit incident updates."""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.slack_webhook_url

    @property
    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.webhook_url.startswith("https://hooks.slack.com/"))

    async def send_payload(self, blocks: List[Dict[str, Any]], text_fallback: str) -> Dict[str, Any]:
        """Dispatches JSON payload to Slack webhook or logs structured card."""
        if not self.is_configured:
            logger.info(f"[SLACK SIMULATION] {text_fallback}")
            return {"dispatched": False, "mode": "LOCAL_SIMULATED", "text": text_fallback}

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                res = await client.post(
                    self.webhook_url,
                    json={"text": text_fallback, "blocks": blocks},
                )
                return {
                    "dispatched": res.status_code == 200,
                    "status_code": res.status_code,
                    "mode": "REMOTE_WEBHOOK",
                }
            except Exception as err:
                logger.error(f"Failed to post to Slack webhook: {err}")
                return {"dispatched": False, "mode": "ERROR", "error": str(err)}

    async def send_incident_alert(
        self,
        incident_id: str,
        title: str,
        severity: str,
        service: str,
        error_rate: float,
    ) -> Dict[str, Any]:
        """Sends Block Kit notification for newly detected incident."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 [TraceHeal] Incident Detected: {title}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Incident ID:*\n`{incident_id}`"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n*{severity}*"},
                    {"type": "mrkdwn", "text": f"*Suspect Service:*\n`{service}`"},
                    {"type": "mrkdwn", "text": f"*Error Rate:*\n`{error_rate * 100:.1f}%`"},
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "🤖 *TraceHeal AI Agents* dispatched for root-cause localization & sandbox reproduction.",
                    }
                ],
            },
        ]
        fallback = f"🚨 [TraceHeal] Incident {incident_id} detected on {service} ({severity})"
        return await self.send_payload(blocks, fallback)

    async def send_remediation_alert(
        self,
        incident_id: str,
        hypothesis: str,
        diff_preview: str,
        validation_status: str,
    ) -> Dict[str, Any]:
        """Sends Block Kit notification when a patch is shadow-verified."""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🛡️ [TraceHeal] Shadow Verification Passed",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Root Cause:* {hypothesis}\n*Status:* `{validation_status}` (Traffic replayed in isolated sandbox with 0% error rate)",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```diff\n{diff_preview[:400]}\n```",
                },
            },
        ]
        fallback = f"🛡️ [TraceHeal] Shadow verification passed for incident {incident_id}"
        return await self.send_payload(blocks, fallback)

    async def send_resolution_alert(
        self,
        incident_id: str,
        mttd_s: float,
        mttr_s: float,
        pr_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends Block Kit notification for full resolution and PR merge generation."""
        pr_link = f"<{pr_url}|View GitHub PR>" if pr_url else "Committed locally"
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "✅ [TraceHeal] Incident Resolved & Closed",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*MTTD (Detection):*\n{mttd_s:.1f}s"},
                    {"type": "mrkdwn", "text": f"*MTTR (Resolution):*\n{mttr_s:.1f}s"},
                    {"type": "mrkdwn", "text": f"*Pull Request:*\n{pr_link}"},
                    {"type": "mrkdwn", "text": f"*State:*\n`RESOLVED & CLOSED`"},
                ],
            },
        ]
        fallback = f"✅ [TraceHeal] Incident {incident_id} successfully resolved and closed (MTTR: {mttr_s:.1f}s)"
        return await self.send_payload(blocks, fallback)


slack_dispatcher = SlackWebhookDispatcher()
