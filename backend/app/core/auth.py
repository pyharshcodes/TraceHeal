"""TraceHeal Enterprise Authentication & Role-Based Access Control (RBAC).

Implements RFC 7519 JSON Web Tokens (JWT) with HS256 digital signatures,
role hierarchy enforcement, and pluggable security policies.
"""

import base64
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import hmac
import json
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    SRE_OPERATOR = "SRE_OPERATOR"
    DEVELOPER_VIEWER = "DEVELOPER_VIEWER"


ROLE_HIERARCHY = {
    UserRole.ADMIN: 30,
    UserRole.SRE_OPERATOR: 20,
    UserRole.DEVELOPER_VIEWER: 10,
}


class UserProfile(BaseModel):
    id: str
    username: str
    full_name: str
    email: str
    role: UserRole
    permissions: List[str]


# Out-of-the-box Enterprise RBAC Accounts
DEMO_USERS: Dict[str, Dict[str, Any]] = {
    "admin": {
        "id": "usr_01_admin",
        "username": "admin",
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
        "full_name": "SRE Platform Architect",
        "email": "architect@traceheal.enterprise",
        "role": UserRole.ADMIN,
        "permissions": ["cluster:write", "chaos:inject", "remediation:apply", "incident:close", "system:admin"],
    },
    "sre_lead": {
        "id": "usr_02_sre",
        "username": "sre_lead",
        "password_hash": hashlib.sha256("sre123".encode()).hexdigest(),
        "full_name": "SRE Incident Commander",
        "email": "sre-lead@traceheal.enterprise",
        "role": UserRole.SRE_OPERATOR,
        "permissions": ["chaos:inject", "remediation:apply", "incident:close", "incident:triage"],
    },
    "viewer": {
        "id": "usr_03_dev",
        "username": "viewer",
        "password_hash": hashlib.sha256("viewer123".encode()).hexdigest(),
        "full_name": "Platform Observer",
        "email": "dev-viewer@traceheal.enterprise",
        "role": UserRole.DEVELOPER_VIEWER,
        "permissions": ["incident:read", "topology:read", "terminal:read"],
    },
}


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4)) if len(data) % 4 else ""
    return base64.urlsafe_b64decode((data + padding).encode())


def create_jwt_token(payload: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed JWT using standard Python HMAC-SHA256."""
    header = {"alg": "HS256", "typ": "JWT"}
    exp = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    claims = {**payload, "exp": int(exp.timestamp())}

    header_bytes = json.dumps(header, separators=(",", ":")).encode()
    claims_bytes = json.dumps(claims, separators=(",", ":")).encode()

    token_segment = f"{_b64_encode(header_bytes)}.{_b64_encode(claims_bytes)}"
    signature = hmac.new(
        settings.jwt_secret_key.encode(),
        token_segment.encode(),
        hashlib.sha256,
    ).digest()

    return f"{token_segment}.{_b64_encode(signature)}"


def verify_jwt_token(token: str) -> Dict[str, Any]:
    """Validates signature and expiration of JWT."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT structure")

        token_segment = f"{parts[0]}.{parts[1]}"
        expected_sig = hmac.new(
            settings.jwt_secret_key.encode(),
            token_segment.encode(),
            hashlib.sha256,
        ).digest()

        actual_sig = _b64_decode(parts[2])
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid token signature")

        claims = json.loads(_b64_decode(parts[1]).decode("utf-8"))
        exp = claims.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            raise ValueError("Token has expired")

        return claims
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"Malformed JWT token: {err}") from err


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> UserProfile:
    """Dependency that extracts user from Authorization header or provides default."""
    if auth and auth.credentials:
        try:
            claims = verify_jwt_token(auth.credentials)
            username = claims.get("sub")
            if username and username in DEMO_USERS:
                u = DEMO_USERS[username]
                return UserProfile(
                    id=u["id"],
                    username=u["username"],
                    full_name=u["full_name"],
                    email=u["email"],
                    role=u["role"],
                    permissions=u["permissions"],
                )
        except ValueError as err:
            if settings.auth_strict_mode:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Authentication failed: {str(err)}",
                )

    if settings.auth_strict_mode:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
        )

    # Permissive default for dashboard/local evaluation
    u = DEMO_USERS["sre_lead"]
    return UserProfile(
        id=u["id"],
        username=u["username"],
        full_name=u["full_name"],
        email=u["email"],
        role=u["role"],
        permissions=u["permissions"],
    )


def require_role(min_role: UserRole):
    """Enforces minimum RBAC role required to access an operational endpoint."""
    async def _role_checker(user: UserProfile = Depends(get_current_user)) -> UserProfile:
        user_weight = ROLE_HIERARCHY.get(user.role, 0)
        req_weight = ROLE_HIERARCHY.get(min_role, 0)

        if user_weight < req_weight:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires role '{min_role.value}', but user possesses '{user.role.value}'.",
            )
        return user

    return _role_checker
