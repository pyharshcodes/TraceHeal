"""TraceHeal Enterprise Authentication Endpoints.

Provides JWT login, current user introspection, and RBAC credential management.
"""

import hashlib
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.app.core.auth import (
    DEMO_USERS,
    UserProfile,
    UserRole,
    create_jwt_token,
    get_current_user,
)

router = APIRouter(prefix="/auth", tags=["Enterprise Authentication & RBAC"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticates against configured enterprise user registry and issues signed JWT."""
    username = req.username.strip().lower()
    user_record = DEMO_USERS.get(username)

    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or credentials.",
        )

    # Validate SHA-256 password hash
    req_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if req_hash != user_record["password_hash"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or credentials.",
        )

    # Issue JWT token
    token = create_jwt_token({
        "sub": username,
        "role": user_record["role"].value,
        "name": user_record["full_name"],
    })

    profile = UserProfile(
        id=user_record["id"],
        username=user_record["username"],
        full_name=user_record["full_name"],
        email=user_record["email"],
        role=user_record["role"],
        permissions=user_record["permissions"],
    )

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=profile,
    )


@router.get("/me", response_model=UserProfile)
async def get_my_profile(current_user: UserProfile = Depends(get_current_user)):
    """Returns the profile and permissions of the currently authenticated SRE operator."""
    return current_user


@router.get("/roles")
async def list_available_roles():
    """Lists enterprise RBAC roles and system permissions hierarchy."""
    return {
        "roles": [
            {
                "role": UserRole.ADMIN.value,
                "tier": 30,
                "description": "Full administrative control, chaos injection, patch application, and cluster management.",
            },
            {
                "role": UserRole.SRE_OPERATOR.value,
                "tier": 20,
                "description": "SRE Incident responder with remediation trigger and chaos injection rights.",
            },
            {
                "role": UserRole.DEVELOPER_VIEWER.value,
                "tier": 10,
                "description": "Read-only access to incident topology, telemetry, and live terminal logs.",
            },
        ],
        "demo_accounts": [
            {"username": "admin", "role": "ADMIN", "default_password": "admin123"},
            {"username": "sre_lead", "role": "SRE_OPERATOR", "default_password": "sre123"},
            {"username": "viewer", "role": "DEVELOPER_VIEWER", "default_password": "viewer123"},
        ],
    }
