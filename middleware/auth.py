import os
import jwt
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, status

JWT_SECRET = os.getenv("JWT_SECRET", "development_jwt_secret_key_32_bytes_super_secure_random")
JWT_ALGORITHM = "HS256"


async def get_current_tenant(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Validates Client JWT (Session JWT or API JWT) and extracts tenant scope.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Missing or malformed Authorization header. Expected Bearer <token>",
                }
            },
        )

    token = authorization.split(" ")[1].strip()

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False},
        )

        role = payload.get("role", "client")
        if role == "super_admin":
            # Super Admin can also access tenant routes if needed, but standard client routes expect tenant context
            return {
                "client_id": payload.get("client_id", "admin_global"),
                "username": payload.get("username", "admin"),
                "role": "super_admin",
                "sub": payload.get("sub"),
                "is_super_admin": True,
            }

        # For client: tenant identifier can be client_id, username, or sub
        raw_client_id = payload.get("client_id")
        username = payload.get("username")
        sub = payload.get("sub")

        if not raw_client_id and not username and not sub:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "INVALID_TOKEN",
                        "message": "Token does not contain a valid tenant identity claim",
                    }
                },
            )

        from config.supabase_client import get_client_by_identifier
        resolved_client = None
        for candidate in [raw_client_id, username, sub]:
            if candidate:
                resolved_client = await get_client_by_identifier(candidate)
                if resolved_client:
                    break

        if resolved_client and resolved_client.get("is_active") is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "ACCOUNT_DEACTIVATED",
                        "message": "This client account has been suspended.",
                    }
                },
            )

        effective_client_id = (
            resolved_client.get("client_id")
            if (resolved_client and resolved_client.get("client_id"))
            else (raw_client_id or username or sub)
        )

        all_keys = list({str(k) for k in [effective_client_id, raw_client_id, username, sub] if k})

        return {
            "client_id": effective_client_id,
            "username": username or (resolved_client.get("username") if resolved_client else None),
            "name": payload.get("name", resolved_client.get("name", "Tenant") if resolved_client else "Tenant"),
            "role": role,
            "token_type": payload.get("type", "session"),
            "sub": payload.get("sub"),
            "all_keys": all_keys,
            "iat": payload.get("iat"),
            "exp": payload.get("exp"),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "TOKEN_EXPIRED",
                    "message": "JWT access token has expired. Please re-authenticate.",
                }
            },
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": f"JWT token signature is invalid: {e}",
                }
            },
        )


async def get_current_admin(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Validates Super Admin JWT. Ensures role is 'super_admin' with no tenant scoping.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Missing or malformed Authorization header. Expected Bearer <admin-token>",
                }
            },
        )

    token = authorization.split(" ")[1].strip()

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False},
        )

        role = payload.get("role")
        if role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "Access restricted: Super Admin privileges required.",
                    }
                },
            )

        return {
            "id": payload.get("sub"),
            "username": payload.get("username"),
            "role": "super_admin",
            "iat": payload.get("iat"),
            "exp": payload.get("exp"),
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "TOKEN_EXPIRED",
                    "message": "Admin session token has expired. Please sign in again.",
                }
            },
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": f"Admin token signature is invalid: {e}",
                }
            },
        )
