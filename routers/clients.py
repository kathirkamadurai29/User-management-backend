import secrets
from datetime import datetime, timezone
import bcrypt
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, status, HTTPException
from middleware.auth import get_current_tenant
from config.supabase_client import (
    get_client_by_identifier,
    generate_and_store_client_credentials,
)
from config.mongodb_client import get_db

router = APIRouter(prefix="/clients", tags=["Clients & Authentication"])


class CredentialsGenerateResponse(BaseModel):
    client_id: str
    client_secret: str
    message: str
    created_at: str


class ClientProfileResponse(BaseModel):
    id: Optional[str] = None
    username: str
    name: str
    email: Optional[str] = None
    client_id: Optional[str] = None
    has_api_credentials: bool
    is_active: bool
    created_at: Optional[str] = None


@router.post(
    "/credentials",
    status_code=status.HTTP_201_CREATED,
    response_model=CredentialsGenerateResponse,
    summary="Generate external API credentials (client_id + client_secret) ONCE for authenticated tenant",
)
async def generate_credentials(tenant: Dict[str, Any] = Depends(get_current_tenant)):
    """
    Generates client_id and client_secret ONCE, bcrypt-hashes the secret, and returns
    the raw secret only this single time for programmatic external API access.
    """
    identifier = tenant.get("username") or tenant.get("sub") or tenant.get("client_id")
    client = await get_client_by_identifier(identifier)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CLIENT_NOT_FOUND", "message": "Authenticated client record not found."}},
        )

    # Check if credentials already exist
    if client.get("client_id") and client.get("client_secret_hash"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "CREDENTIALS_ALREADY_GENERATED",
                    "message": "API credentials have already been generated for this client. The secret cannot be retrieved or regenerated.",
                    "client_id": client.get("client_id"),
                }
            },
        )

    # Generate client_id and client_secret
    client_id = f"cli_{secrets.token_hex(10)}"
    raw_secret = f"sec_{secrets.token_hex(24)}"

    # Bcrypt-hash the secret
    salt = bcrypt.gensalt(rounds=10)
    secret_hash = bcrypt.hashpw(raw_secret.encode("utf-8"), salt).decode("utf-8")

    try:
        await generate_and_store_client_credentials(
            client_identifier=identifier,
            client_id=client_id,
            client_secret_hash=secret_hash,
        )

        # Migrate any user records in MongoDB scoped by username to the new client_id
        db = get_db()
        if db is not None:
            old_tenant_id = client.get("username")
            if old_tenant_id and old_tenant_id != client_id:
                db["users"].update_many({"client_id": old_tenant_id}, {"$set": {"client_id": client_id}})
                db["activity_logs"].update_many({"client_id": old_tenant_id}, {"$set": {"client_id": client_id}})

        return CredentialsGenerateResponse(
            client_id=client_id,
            client_secret=raw_secret,
            message="External API credentials generated successfully. Save this secret now; it will NEVER be displayed again.",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "CREDENTIAL_GENERATION_FAILED", "message": str(e)}},
        )


@router.get(
    "/me",
    response_model=ClientProfileResponse,
    summary="Get current authenticated client profile and credential status",
)
async def get_profile(tenant: Dict[str, Any] = Depends(get_current_tenant)):
    identifier = tenant.get("username") or tenant.get("sub") or tenant.get("client_id")
    client = await get_client_by_identifier(identifier)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CLIENT_NOT_FOUND", "message": "Client profile not found."}},
        )

    has_creds = bool(client.get("client_id") and client.get("client_secret_hash"))

    return ClientProfileResponse(
        id=str(client.get("id")),
        username=client.get("username", tenant.get("username", "client")),
        name=client.get("name", client.get("username", "Tenant")),
        email=client.get("email"),
        client_id=client.get("client_id"),
        has_api_credentials=has_creds,
        is_active=client.get("is_active", True),
        created_at=client.get("created_at"),
    )
