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
        client_id = payload.get("client_id") or payload.get("username") or payload.get("sub")
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": {
                        "code": "INVALID_TOKEN",
                        "message": "Token does not contain a valid tenant identity claim",
                    }
                },
            )

        return {
            "client_id": client_id,
            "username": payload.get("username"),
            "name": payload.get("name", payload.get("username", "Tenant")),
            "role": role,
            "token_type": payload.get("type", "session"),
            "sub": payload.get("sub"),
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
