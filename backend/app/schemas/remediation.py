"""Pydantic models for Remediation, Policy Verification, and Shadow Deployment."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class RemediationProposalCreate(BaseModel):
    """Input payload to propose a remediation."""
    incident_id: str
    hypothesis_id: Optional[str] = None
    patch_type: Literal["CONFIG", "CODE", "CANARY_ROLLBACK"] = "CONFIG"
    target_service: str
    diff_content: str
    rollback_diff: Optional[str] = None
    config_parameters: Optional[Dict[str, Any]] = None


class RemediationProposalRead(BaseModel):
    """Detailed serialization of a remediation record."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_id: str
    hypothesis_id: Optional[str] = None
    patch_type: str
    target_service: str
    diff_content: str
    rollback_diff: Optional[str] = None
    policy_check_status: str
    policy_violations_json: Optional[str] = None
    validation_status: str
    validation_details_json: Optional[str] = None
    approval_status: str
    applied_at: Optional[datetime] = None
    created_at: datetime


class PolicyCheckResult(BaseModel):
    """Result of automated safety and security guardrail evaluation."""
    status: Literal["PASSED", "REJECTED"]
    violations: List[str] = Field(default_factory=list)
    passed_rules: List[str] = Field(default_factory=list)
    evaluated_rules: List[str] = Field(default_factory=list)
    evaluated_at: str


class ShadowValidationResult(BaseModel):
    """Outcome of validating a remediation patch in the isolated sandbox."""
    status: Literal["VALIDATED", "FAILED"]
    sandbox_id: str
    pre_patch_errors: int
    post_patch_errors: int
    error_rate: float
    latency_p95_ms: float
    reproduced_issue_resolved: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class ApprovalRequest(BaseModel):
    """Human-in-the-loop or policy approval decision."""
    decision: Literal["APPROVE", "REJECT"] = "APPROVE"
    approver: str = Field(default="SRE_LEAD")
    notes: Optional[str] = None


class ApplyRemediationRequest(BaseModel):
    """Request to deploy an approved patch to the live service."""
    target_base_url: Optional[str] = None
    force: Optional[bool] = False
