import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import bcrypt
import jwt
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, status
from config.supabase_client import (
    get_client_by_username,
    get_client_by_client_id,
    insert_client_account,
)

router = APIRouter(prefix="/auth", tags=["Clients & Authentication"])

JWT_SECRET = os.getenv("JWT_SECRET", "development_jwt_secret_key_32_bytes_super_secure_random")
JWT_ALGORITHM = "HS256"


# ==========================================
# SCHEMAS
# ==========================================

class ClientRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Login identity")
    password: str = Field(..., min_length=6, description="Account password")
    name: Optional[str] = Field(None, description="Organization or client display name")
    email: Optional[str] = Field(None, description="Contact email")


class ClientRegisterResponse(BaseModel):
    message: str
    username: str
    name: str
    created_at: str


class ClientLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ClientInfo(BaseModel):
    id: Optional[str] = None
    username: str
    name: str
    email: Optional[str] = None
    client_id: Optional[str] = None
    has_api_credentials: bool = False


class SessionAuthResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: str = "24h"
    client: ClientInfo


class ApiTokenRequest(BaseModel):
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)


class ApiTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: str = "24h"
    client_id: str


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ClientRegisterResponse,
    summary="Client sign up with username + password only (no client_id/secret yet)",
)
async def register(body: ClientRegisterRequest):
    username = body.username.strip().lower()
    existing = await get_client_by_username(username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "USERNAME_EXISTS",
                    "message": f"A client with username '{username}' already exists.",
                }
            },
        )

    # Hash password with bcrypt
    salt = bcrypt.gensalt(rounds=10)
    password_hash = bcrypt.hashpw(body.password.encode("utf-8"), salt).decode("utf-8")

    try:
        created = await insert_client_account(
            username=username,
            password_hash=password_hash,
            name=body.name.strip() if body.name else username,
            email=body.email.strip().lower() if body.email else None,
        )
        return ClientRegisterResponse(
            message="Client account registered successfully.",
            username=created["username"],
            name=created.get("name", created["username"]),
            created_at=created.get("created_at", datetime.now(timezone.utc).isoformat()),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "REGISTRATION_ERROR", "message": str(e)}},
        )


@router.post(
    "/login",
    response_model=SessionAuthResponse,
    summary="Client login with username + password yielding Session JWT for dashboard",
)
async def login(body: ClientLoginRequest):
    username = body.username.strip().lower()
    password = body.password

    client = await get_client_by_username(username)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."}},
        )

    if client.get("is_active") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "ACCOUNT_DEACTIVATED", "message": "This client account has been suspended."}},
        )

    stored_hash = client.get("password_hash")
    if not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "PASSWORD_NOT_SET", "message": "Account was created with legacy credentials. Please contact administrator."}},
        )

    try:
        is_match = bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        is_match = False

    if not is_match:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."}},
        )

    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=24)

    effective_tenant_id = client.get("client_id") or client.get("username") or str(client.get("id"))

    token_payload = {
        "sub": str(client.get("id", client["username"])),
        "username": client["username"],
        "name": client.get("name", client["username"]),
        "client_id": effective_tenant_id,
        "role": "client",
        "type": "session",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "user-management-platform",
        "aud": "tenant-dashboard",
    }

    session_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    has_creds = bool(client.get("client_id") and client.get("client_secret_hash"))

    return SessionAuthResponse(
        access_token=session_token,
        token_type="Bearer",
        expires_in="24h",
        client=ClientInfo(
            id=str(client.get("id")),
            username=client["username"],
            name=client.get("name", client["username"]),
            email=client.get("email"),
            client_id=client.get("client_id"),
            has_api_credentials=has_creds,
        ),
    )


@router.post(
    "/token",
    response_model=ApiTokenResponse,
    summary="External API consumer exchanges client_id + client_secret for API JWT",
)
async def exchange_api_token(body: ApiTokenRequest):
    client_id = body.client_id.strip()
    client_secret = body.client_secret.strip()

    record = await get_client_by_client_id(client_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "External API client credentials could not be verified."}},
        )

    if record.get("is_active") is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "CLIENT_DEACTIVATED", "message": "This client account has been suspended."}},
        )

    stored_hash = record.get("client_secret_hash", "")
    if not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "NO_API_CREDENTIALS", "message": "No API secret configured for this client."}},
        )

    try:
        is_match = bcrypt.checkpw(client_secret.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        is_match = False

    if not is_match:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "External API client credentials could not be verified."}},
        )

    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=24)

    token_payload = {
        "sub": str(record.get("id", record["client_id"])),
        "client_id": record["client_id"],
        "username": record.get("username"),
        "role": "client",
        "type": "api",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "user-management-platform",
        "aud": "external-api",
    }

    api_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return ApiTokenResponse(
        access_token=api_token,
        token_type="Bearer",
        expires_in="24h",
        client_id=record["client_id"],
    )
