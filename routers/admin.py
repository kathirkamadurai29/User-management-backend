import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Literal
from bson import ObjectId
import bcrypt
import jwt
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status

from middleware.auth import get_current_admin
from config.supabase_client import (
    get_admin_by_username,
    list_all_clients,
    get_client_by_identifier,
    update_client_status,
    delete_client_account,
)
from config.mongodb_client import get_db
from config.firebase_client import upload_profile_picture
from routers.users import _clean_doc, _process_avatar_base64

router = APIRouter(prefix="/admin", tags=["Super Admin Engine"])

JWT_SECRET = os.getenv("JWT_SECRET", "development_jwt_secret_key_32_bytes_super_secure_random")
JWT_ALGORITHM = "HS256"


# ==========================================
# SCHEMAS
# ==========================================

class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: str = "24h"
    role: str = "super_admin"
    admin: Dict[str, Any]


class ClientStatusRequest(BaseModel):
    is_active: bool


class AdminUserCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"
    status: Literal["active", "inactive", "pending"] = "active"
    avatar_url: Optional[str] = None
    avatar_base64: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AdminUserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    role: Optional[Literal["admin", "member", "viewer"]] = None
    status: Optional[Literal["active", "inactive", "pending"]] = None
    avatar_url: Optional[str] = None
    avatar_base64: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ==========================================
# ADMIN AUTHENTICATION
# ==========================================

@router.post(
    "/auth/login",
    response_model=AdminLoginResponse,
    summary="Authenticate Super Admin with username + password (no client_id, no tenant scoping)",
)
async def admin_login(body: AdminLoginRequest):
    username = body.username.strip().lower()
    password = body.password

    admin = await get_admin_by_username(username)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_ADMIN_CREDENTIALS", "message": "Super Admin authentication failed."}},
        )

    stored_hash = admin.get("password_hash")
    if not stored_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_ADMIN_CREDENTIALS", "message": "Admin password hash not found."}},
        )

    try:
        is_match = bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        is_match = False

    if not is_match:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_ADMIN_CREDENTIALS", "message": "Super Admin authentication failed."}},
        )

    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=24)

    token_payload = {
        "sub": str(admin.get("id", admin["username"])),
        "username": admin["username"],
        "role": "super_admin",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "user-management-platform",
        "aud": "super-admin-portal",
    }

    admin_token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return AdminLoginResponse(
        access_token=admin_token,
        token_type="Bearer",
        expires_in="24h",
        role="super_admin",
        admin={
            "id": str(admin.get("id")),
            "username": admin["username"],
            "role": "super_admin",
        },
    )


# ==========================================
# TENANT / CLIENT MANAGEMENT (BYPASSES ISOLATION)
# ==========================================

@router.get(
    "/clients",
    summary="List all registered platform clients with user counts and statuses",
)
async def get_all_clients(admin: Dict[str, Any] = Depends(get_current_admin)):
    clients = await list_all_clients()
    db = get_db()

    enriched = []
    for c in clients:
        c_copy = dict(c)
        # Count users in MongoDB for this client
        user_count = 0
        if db is not None:
            possible_keys = [
                k for k in [c.get("client_id"), c.get("username"), str(c.get("id"))]
                if k
            ]
            user_count = db["users"].count_documents({
                "client_id": {"$in": possible_keys},
                "is_deleted": False,
            })
        c_copy["user_count"] = user_count
        c_copy["has_api_credentials"] = bool(c.get("client_id") and c.get("client_secret_hash"))
        enriched.append(c_copy)

    clients_with_creds = sum(1 for c in enriched if c.get("has_api_credentials"))
    clients_without_creds = len(enriched) - clients_with_creds
    credentials_count = {
        "clients_with_credentials": clients_with_creds,
        "clients_without_credentials": clients_without_creds,
        "total_credentials": clients_with_creds,
    }

    return {
        "clients": enriched,
        "total": len(enriched),
        "credentials_count": credentials_count,
    }


# ==========================================
# ALL REGISTERED USERS DIRECTORY (PLATFORM-WIDE)
# ==========================================

@router.get(
    "/users",
    summary="List all registered platform users across all clients/tenants with search and filters",
)
async def get_all_platform_users(
    search: Optional[str] = Query(None, description="Search by name, email, or client_id"),
    status: Optional[str] = Query(None, description="Filter by status: active, inactive, pending"),
    role: Optional[str] = Query(None, description="Filter by role: admin, member, viewer"),
    client_id: Optional[str] = Query(None, description="Filter by specific client ID or username"),
    limit: int = Query(50, ge=1, le=500),
    skip: int = Query(0, ge=0),
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    db = get_db()
    users_col = db["users"]

    query: Dict[str, Any] = {
        "is_deleted": False,
    }

    if status and status != "all":
        query["status"] = status.lower()

    if role and role != "all":
        query["role"] = role.lower()

    if client_id and client_id != "all":
        query["client_id"] = client_id.strip()

    if search and search.strip():
        term = search.strip()
        query["$or"] = [
            {"name": {"$regex": term, "$options": "i"}},
            {"email": {"$regex": term, "$options": "i"}},
            {"client_id": {"$regex": term, "$options": "i"}},
        ]

    cursor = users_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    raw_users = [_clean_doc(doc) for doc in cursor]
    total = users_col.count_documents(query)

    # Build client lookup map to enrich user records with client display details
    clients = await list_all_clients()
    client_map = {}
    for c in clients:
        c_name = c.get("name") or c.get("username") or "Tenant"
        c_user = c.get("username")
        for k in [c.get("client_id"), c.get("username"), str(c.get("id"))]:
            if k:
                client_map[k] = {"name": c_name, "username": c_user}

    enriched_users = []
    for u in raw_users:
        u_copy = dict(u)
        c_info = client_map.get(u.get("client_id"), {})
        u_copy["client_name"] = c_info.get("name") or u.get("client_id")
        u_copy["client_username"] = c_info.get("username")
        enriched_users.append(u_copy)

    return {
        "users": enriched_users,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@router.patch(
    "/clients/{client_id}/status",
    summary="Activate or deactivate any client",
)
async def set_client_status(
    client_id: str,
    body: ClientStatusRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    updated = await update_client_status(client_id, body.is_active)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CLIENT_NOT_FOUND", "message": f"Client '{client_id}' not found."}},
        )
    return {
        "message": f"Client status updated to {'active' if body.is_active else 'inactive'}.",
        "client": updated,
    }


@router.delete(
    "/clients/{client_id}",
    summary="Deactivate or delete any client and deactivate their users",
)
async def delete_client(
    client_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    client = await get_client_by_identifier(client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CLIENT_NOT_FOUND", "message": f"Client '{client_id}' not found."}},
        )

    # Deactivate in Supabase
    await delete_client_account(client_id)

    # Soft-delete all client's users in MongoDB
    db = get_db()
    if db is not None:
        possible_keys = [
            k for k in [client.get("client_id"), client.get("username"), str(client.get("id"))]
            if k
        ]
        db["users"].update_many(
            {"client_id": {"$in": possible_keys}},
            {"$set": {"is_deleted": True, "status": "inactive", "deleted_at": datetime.now(timezone.utc).isoformat()}},
        )

    return {"message": f"Client '{client_id}' and all associated tenant records successfully removed."}


# ==========================================
# CLIENT USERS DRILL-DOWN & FULL CRUD
# ==========================================

@router.get(
    "/clients/{client_id}/users",
    summary="Drill into any client's users directory with search and status filters",
)
async def get_client_users(
    client_id: str,
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    client = await get_client_by_identifier(client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CLIENT_NOT_FOUND", "message": f"Client '{client_id}' not found."}},
        )

    db = get_db()
    users_col = db["users"]

    possible_keys = [
        k for k in [client.get("client_id"), client.get("username"), str(client.get("id"))]
        if k
    ]

    query: Dict[str, Any] = {
        "client_id": {"$in": possible_keys},
        "is_deleted": False,
    }

    if status and status != "all":
        query["status"] = status.lower()

    if search and search.strip():
        term = search.strip()
        query["$or"] = [
            {"name": {"$regex": term, "$options": "i"}},
            {"email": {"$regex": term, "$options": "i"}},
        ]

    cursor = users_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    items = [_clean_doc(doc) for doc in cursor]
    total = users_col.count_documents(query)

    return {
        "client": {
            "id": str(client.get("id")),
            "username": client.get("username"),
            "name": client.get("name"),
            "client_id": client.get("client_id"),
            "is_active": client.get("is_active", True),
        },
        "users": items,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@router.post(
    "/clients/{client_id}/users",
    status_code=status.HTTP_201_CREATED,
    summary="Create a user under any specified client",
)
async def admin_create_client_user(
    client_id: str,
    body: AdminUserCreateRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    client = await get_client_by_identifier(client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "CLIENT_NOT_FOUND", "message": f"Client '{client_id}' not found."}},
        )

    effective_client_id = client.get("client_id") or client.get("username") or str(client.get("id"))

    db = get_db()
    users_col = db["users"]

    # Check for duplicate email under this client
    possible_keys = [
        k for k in [client.get("client_id"), client.get("username"), str(client.get("id"))]
        if k
    ]
    existing = users_col.find_one({
        "client_id": {"$in": possible_keys},
        "email": str(body.email).lower(),
        "is_deleted": False,
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "USER_ALREADY_EXISTS", "message": f"Email '{body.email}' already exists for client '{client_id}'."}},
        )

    # Process avatar upload
    avatar_url = body.avatar_url
    if body.avatar_base64:
        uploaded = _process_avatar_base64(
            body.avatar_base64,
            client_id=effective_client_id,
            identifier=str(body.email).replace("@", "_").replace(".", "_"),
        )
        if uploaded:
            avatar_url = uploaded

    now_iso = datetime.now(timezone.utc).isoformat()
    new_user = {
        "client_id": effective_client_id,
        "name": body.name.strip(),
        "email": str(body.email).lower(),
        "role": body.role,
        "status": body.status,
        "avatar_url": avatar_url,
        "metadata": body.metadata or {},
        "is_deleted": False,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    insert_res = users_col.insert_one(new_user)
    new_user["_id"] = str(insert_res.inserted_id)

    return _clean_doc(new_user)


@router.get(
    "/clients/{client_id}/users/{user_id}",
    summary="Get single user from any client",
)
async def admin_get_client_user(
    client_id: str,
    user_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    db = get_db()
    id_filter = [user_id]
    if ObjectId.is_valid(user_id):
        id_filter.append(ObjectId(user_id))

    user = db["users"].find_one({"_id": {"$in": id_filter}, "is_deleted": False})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}},
        )
    return _clean_doc(user)


@router.put(
    "/clients/{client_id}/users/{user_id}",
    summary="Update user under any client",
)
async def admin_update_client_user(
    client_id: str,
    user_id: str,
    body: AdminUserUpdateRequest,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    db = get_db()
    users_col = db["users"]

    id_filter = [user_id]
    if ObjectId.is_valid(user_id):
        id_filter.append(ObjectId(user_id))

    existing = users_col.find_one({"_id": {"$in": id_filter}, "is_deleted": False})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}},
        )

    updates: Dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.role is not None:
        updates["role"] = body.role
    if body.status is not None:
        updates["status"] = body.status
    if body.metadata is not None:
        updates["metadata"] = body.metadata

    if body.avatar_base64:
        uploaded = _process_avatar_base64(
            body.avatar_base64,
            client_id=existing.get("client_id", client_id),
            identifier=user_id,
        )
        if uploaded:
            updates["avatar_url"] = uploaded
    elif body.avatar_url is not None:
        updates["avatar_url"] = body.avatar_url

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    users_col.update_one({"_id": {"$in": id_filter}}, {"$set": updates})
    updated = users_col.find_one({"_id": {"$in": id_filter}})
    return _clean_doc(updated)


@router.delete(
    "/clients/{client_id}/users/{user_id}",
    summary="Deactivate/delete user under any client",
)
async def admin_delete_client_user(
    client_id: str,
    user_id: str,
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    db = get_db()
    users_col = db["users"]

    id_filter = [user_id]
    if ObjectId.is_valid(user_id):
        id_filter.append(ObjectId(user_id))

    existing = users_col.find_one({"_id": {"$in": id_filter}, "is_deleted": False})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found."}},
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    users_col.update_one({"_id": {"$in": id_filter}}, {
        "$set": {
            "is_deleted": True,
            "status": "inactive",
            "deleted_at": now_iso,
            "updated_at": now_iso,
        }
    })

    return {"message": "User deactivated successfully by Super Admin", "id": user_id}


# ==========================================
# PLATFORM-WIDE TELEMETRY / ACTIVITY LOGS
# ==========================================

@router.get(
    "/activity",
    summary="View platform-wide request activity logs across all tenants",
)
async def get_platform_activity(
    limit: int = Query(100, ge=1, le=500),
    admin: Dict[str, Any] = Depends(get_current_admin),
):
    db = get_db()
    logs_col = db["activity_logs"]

    cursor = logs_col.find({}).sort("timestamp", -1).limit(limit)
    logs = [_clean_doc(l) for l in cursor]

    # Metrics calculation
    status_2xx = 0
    status_4xx = 0
    status_5xx = 0
    endpoint_counts: Dict[str, int] = {}
    active_tenants = set()

    for log in logs:
        s = log.get("status", 200)
        if 200 <= s < 300:
            status_2xx += 1
        elif 400 <= s < 500:
            status_4xx += 1
        elif s >= 500:
            status_5xx += 1

        ep = f"{log.get('method', 'GET')} {log.get('endpoint', '')}".strip()
        endpoint_counts[ep] = endpoint_counts.get(ep, 0) + 1

        c_id = log.get("client_id")
        if c_id:
            active_tenants.add(c_id)

    total_requests = len(logs)
    success_rate = round((status_2xx / total_requests) * 100, 1) if total_requests > 0 else 100.0

    return {
        "metrics": {
            "total_requests": total_requests,
            "status_2xx": status_2xx,
            "status_4xx": status_4xx,
            "status_5xx": status_5xx,
            "success_rate_percent": success_rate,
            "active_tenants_count": len(active_tenants),
            "endpoints_breakdown": endpoint_counts,
        },
        "logs": logs[:limit],
    }


# ==========================================
# PLATFORM OVERVIEW & ENDPOINTS USAGE STATS
# ==========================================

@router.get(
    "/stats",
    summary="Platform-wide statistics: registered users, clients credentials count, and endpoints usage stats",
)
@router.get(
    "/overview",
    summary="Platform overview alias for Super Admin",
    include_in_schema=False,
)
async def get_platform_stats(admin: Dict[str, Any] = Depends(get_current_admin)):
    db = get_db()
    clients = await list_all_clients()

    # Client Credentials Statistics
    total_clients = len(clients)
    clients_with_credentials = sum(1 for c in clients if c.get("client_id") and c.get("client_secret_hash"))
    clients_without_credentials = total_clients - clients_with_credentials
    active_clients = sum(1 for c in clients if c.get("is_active", True) is not False)
    inactive_clients = total_clients - active_clients
    adoption_rate = round((clients_with_credentials / total_clients) * 100, 1) if total_clients > 0 else 0.0

    # Users Statistics
    users_col = db["users"]
    total_users = users_col.count_documents({"is_deleted": False})
    active_users = users_col.count_documents({"is_deleted": False, "status": "active"})
    pending_users = users_col.count_documents({"is_deleted": False, "status": "pending"})
    inactive_users = users_col.count_documents({"is_deleted": False, "status": "inactive"})
    deleted_users = users_col.count_documents({"is_deleted": True})

    # Endpoints Usage Stats from activity telemetry
    logs_col = db["activity_logs"]
    total_logs_count = logs_col.count_documents({})
    logs_cursor = logs_col.find({}).sort("timestamp", -1).limit(1000)
    logs = [_clean_doc(l) for l in logs_cursor]

    status_2xx = 0
    status_4xx = 0
    status_5xx = 0
    endpoint_counts: Dict[str, int] = {}
    method_counts: Dict[str, int] = {}
    active_tenants = set()

    for log in logs:
        s = log.get("status", 200)
        if 200 <= s < 300:
            status_2xx += 1
        elif 400 <= s < 500:
            status_4xx += 1
        elif s >= 500:
            status_5xx += 1

        method = log.get("method", "GET").upper()
        method_counts[method] = method_counts.get(method, 0) + 1

        ep = f"{method} {log.get('endpoint', '')}".strip()
        endpoint_counts[ep] = endpoint_counts.get(ep, 0) + 1

        c_id = log.get("client_id")
        if c_id and c_id != "anonymous":
            active_tenants.add(c_id)

    total_analyzed = len(logs)
    success_rate = round((status_2xx / total_analyzed) * 100, 1) if total_analyzed > 0 else 100.0

    # Top endpoints sorted by call count
    top_endpoints = [
        {"endpoint": ep, "count": count, "percentage": round((count / total_analyzed) * 100, 1)}
        for ep, count in sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ] if total_analyzed > 0 else []

    return {
        "users_stats": {
            "total_registered_users": total_users,
            "active_users": active_users,
            "pending_users": pending_users,
            "inactive_users": inactive_users,
            "deleted_users": deleted_users,
        },
        "clients_stats": {
            "total_clients": total_clients,
            "active_clients": active_clients,
            "inactive_clients": inactive_clients,
        },
        "credentials_stats": {
            "total_clients": total_clients,
            "clients_with_credentials": clients_with_credentials,
            "clients_without_credentials": clients_without_credentials,
            "credentials_adoption_rate_percent": adoption_rate,
        },
        "endpoints_usage_stats": {
            "total_telemetry_requests": total_logs_count,
            "sampled_requests": total_analyzed,
            "success_rate_percent": success_rate,
            "status_2xx": status_2xx,
            "status_4xx": status_4xx,
            "status_5xx": status_5xx,
            "method_breakdown": method_counts,
            "endpoints_breakdown": endpoint_counts,
            "top_endpoints": top_endpoints,
            "active_tenants_count": len(active_tenants),
        },
    }
