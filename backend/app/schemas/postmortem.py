"""Pydantic schemas for Postmortem Dossiers, Git Pull Requests, and Recovery Validation."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PostmortemActionItem(BaseModel):
    priority: str = Field(..., description="P0, P1, P2")
    category: str = Field(..., description="Configuration, Observability, Code, Resilience")
    description: str
    owner: str = Field(default="SRE_TEAM")


class PostmortemTimelineEntry(BaseModel):
    timestamp: str
    event: str
    actor: str
    details: Optional[str] = None


class PostmortemReport(BaseModel):
    """Complete engineering postmortem review dossier."""
    incident_id: str
    title: str
    severity: str
    status: str
    suspect_service: str
    detected_at: str
    remediated_at: Optional[str] = None
    resolved_at: Optional[str] = None
    mttd_seconds: float
    mttr_seconds: float
    root_cause_analysis: str
    empirical_verification_proof: str
    remediation_summary: str
    shadow_validation_benchmark: Dict[str, Any] = Field(default_factory=dict)
    timeline: List[PostmortemTimelineEntry] = Field(default_factory=list)
    action_items: List[PostmortemActionItem] = Field(default_factory=list)
    markdown: str


class PullRequestDossier(BaseModel):
    """Git Pull Request specification and committed patch metadata."""
    incident_id: str
    branch_name: str
    title: str
    body_markdown: str
    patch_diff: str
    commit_hash: Optional[str] = None
    target_service: str
    status: str = Field(default="CREATED")
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    created_at: str


class RecoveryValidationResult(BaseModel):
    """Result of post-remediation cluster health and checkout traffic validation."""
    incident_id: str
    status: str  # RESOLVED, UNHEALTHY
    cluster_health: Dict[str, Any] = Field(default_factory=dict)
    baseline_transactions_succeeded: int
    baseline_transactions_failed: int
    recovery_confirmed: bool
    validated_at: str
    details: Dict[str, Any] = Field(default_factory=dict)
