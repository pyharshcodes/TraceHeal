"""Remediation & Policy Guardrail API Endpoints."""

import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.remediation_agent import RemediationAgent
from backend.app.core.auth import UserProfile, UserRole, require_role
from backend.app.db.models import Remediation
from backend.app.db.session import get_db
from backend.app.remediation.deployer import RemediationDeployer
from backend.app.remediation.policy_engine import PolicyEngine
from backend.app.remediation.polyglot import LanguageValidationResult, PolyglotEngine, SupportedLanguage
from backend.app.schemas.remediation import (
    ApplyRemediationRequest,
    ApprovalRequest,
    PolicyCheckResult,
    RemediationProposalRead,
    ShadowValidationResult,
)

router = APIRouter(prefix="/remediations", tags=["Remediation"])
agent = RemediationAgent()
deployer = RemediationDeployer()


class ProposeRemediationBody(BaseModel):
    incident_id: str
    hypothesis_id: Optional[str] = None
    service_name: Optional[str] = None
    remediation_type: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@router.post("/propose", response_model=RemediationProposalRead)
async def propose_remediation_json(
    req: ProposeRemediationBody,
    db: AsyncSession = Depends(get_db),
):
    """Generates a policy-checked remediation proposal from an incident payload."""
    try:
        remediation = await agent.propose_remediation(db, req.incident_id, req.hypothesis_id)
        return remediation
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/propose/{incident_id}", response_model=RemediationProposalRead)
async def propose_remediation(
    incident_id: str,
    hypothesis_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Generates a policy-checked configuration/code remediation proposal from a verified root cause."""
    try:
        remediation = await agent.propose_remediation(db, incident_id, hypothesis_id)
        return remediation
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{remediation_id}/policy-check", response_model=PolicyCheckResult)
async def evaluate_policy(
    remediation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Re-evaluates security and safety guardrails for an existing proposal."""
    stmt = select(Remediation).where(Remediation.id == remediation_id)
    res = await db.execute(stmt)
    rem = res.scalar_one_or_none()
    if not rem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Remediation '{remediation_id}' not found.")

    policy_res = PolicyEngine.evaluate(
        target_service=rem.target_service,
        diff_content=rem.diff_content,
        patch_type=rem.patch_type,
        rollback_diff=rem.rollback_diff,
    )

    rem.policy_check_status = policy_res.status
    rem.policy_violations_json = json.dumps(policy_res.violations) if policy_res.violations else None
    await db.commit()
    return policy_res


@router.post("/{remediation_id}/shadow-validate", response_model=ShadowValidationResult)
async def shadow_validate_remediation(
    remediation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Spins up an isolated sandbox, applies patch, and verifies regression-free incident resolution."""
    try:
        val_res = await deployer.execute_shadow_validation(db, remediation_id)
        return val_res
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{remediation_id}/approve", response_model=RemediationProposalRead)
async def approve_remediation(
    remediation_id: str,
    req: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
):
    """Human-in-the-loop or policy gatekeeper approval of a shadow-validated remediation."""
    try:
        rem = await deployer.approve_remediation(
            db=db,
            remediation_id=remediation_id,
            approver=req.approver,
            decision=req.decision,
            notes=req.notes,
        )
        return rem
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{remediation_id}/apply")
async def apply_remediation(
    remediation_id: str,
    req: ApplyRemediationRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_role(UserRole.SRE_OPERATOR)),
):
    """Applies an approved patch to the live target service with automatic canary rollback."""
    try:
        result = await deployer.apply_remediation(
            db=db,
            remediation_id=remediation_id,
            target_base_url=req.target_base_url,
            force=bool(req.force),
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/{remediation_id}/rollback")
async def rollback_remediation(
    remediation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Executes manual rollback of an applied patch."""
    try:
        result = await deployer.rollback_remediation(db=db, remediation_id=remediation_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{remediation_id}", response_model=RemediationProposalRead)
async def get_remediation(
    remediation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieves remediation details, policy check outcome, and validation dossier."""
    stmt = select(Remediation).where(Remediation.id == remediation_id)
    res = await db.execute(stmt)
    rem = res.scalar_one_or_none()
    if not rem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Remediation '{remediation_id}' not found.")
    return rem


@router.get("/incident/{incident_id}", response_model=List[RemediationProposalRead])
async def list_incident_remediations(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Lists all remediations generated for a specific incident."""
    stmt = select(Remediation).where(Remediation.incident_id == incident_id).order_by(Remediation.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


class PolyglotValidateRequest(BaseModel):
    code: str
    filename: Optional[str] = None
    language: Optional[str] = None


@router.post("/polyglot-check", response_model=LanguageValidationResult)
async def polyglot_check(req: PolyglotValidateRequest):
    """Analyzes AST and security guardrails across Python, Go, and Node.js/TypeScript."""
    lang_override = None
    if req.language:
        try:
            lang_override = SupportedLanguage(req.language.lower())
        except ValueError:
            pass

    return PolyglotEngine.evaluate_polyglot_patch(
        code=req.code,
        filename=req.filename,
        language_override=lang_override,
    )
