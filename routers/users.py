import base64
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from middleware.auth import get_current_tenant
from config.mongodb_client import get_db
from config.firebase_client import upload_profile_picture

router = APIRouter(prefix="/users", tags=["Users Management"])


# ==========================================
# SCHEMAS
# ==========================================

class UserCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"
    status: Literal["active", "inactive", "pending"] = "active"
    avatar_url: Optional[str] = None
    avatar_base64: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    role: Optional[Literal["admin", "member", "viewer"]] = None
    status: Optional[Literal["active", "inactive", "pending"]] = None
    avatar_url: Optional[str] = None
    avatar_base64: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UserResponse(BaseModel):
    id: str = Field(..., alias="_id")
    client_id: str
    name: str
    email: str
    role: str
    status: str
    avatar_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_deleted: bool
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        populate_by_name = True


class UsersListResponse(BaseModel):
    users: List[Dict[str, Any]]
    total: int
    limit: int
    skip: int


def _clean_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    clean = dict(doc)
    if "_id" in clean:
        clean["_id"] = str(clean["_id"])
    return clean


def _get_tenant_keys(tenant: Dict[str, Any]) -> List[str]:
    keys = list(tenant.get("all_keys") or [])
    if tenant.get("client_id") and tenant["client_id"] not in keys:
        keys.append(tenant["client_id"])
    if tenant.get("username") and tenant["username"] not in keys:
        keys.append(tenant["username"])
    return keys or ["default"]


def _process_avatar_base64(avatar_base64: str, client_id: str, identifier: str) -> Optional[str]:
    """Helper to decode base64 image data and upload to Firebase Storage."""
    if not avatar_base64 or not avatar_base64.strip():
        return None

    try:
        content_type = "image/jpeg"
        raw_b64 = avatar_base64.strip()
        if raw_b64.startswith("data:") and ";base64," in raw_b64:
            header, raw_b64 = raw_b64.split(";base64,", 1)
            content_type = header.replace("data:", "").strip() or "image/jpeg"

        file_bytes = base64.b64decode(raw_b64)
        ext = content_type.split("/")[-1] if "/" in content_type else "jpg"
        filename = f"{identifier}.{ext}"

        return upload_profile_picture(
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            client_id=client_id,
        )
    except Exception as e:
        print(f"[Firebase Avatar] Base64 processing notice: {e}")
        return avatar_base64 if avatar_base64.startswith("http") else None


# ==========================================
# ENDPOINTS
# ==========================================

@router.post(
    "/upload-avatar",
    summary="Upload user avatar image directly to Firebase Storage via multipart/form-data",
)
async def upload_avatar_endpoint(
    file: UploadFile = File(...),
    tenant: Dict[str, Any] = Depends(get_current_tenant),
):
    client_id = tenant["client_id"]
    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "EMPTY_FILE", "message": "Uploaded file is empty."}},
        )

    public_url = upload_profile_picture(
        file_bytes=contents,
        filename=file.filename or "avatar.jpg",
        content_type=file.content_type or "image/jpeg",
        client_id=client_id,
    )

    return {"avatar_url": public_url}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create user scoped strictly to authenticated tenant",
)
async def create_user(
    body: UserCreateRequest,
    tenant: Dict[str, Any] = Depends(get_current_tenant),
):
    client_id = tenant["client_id"]
    db = get_db()
    users_col = db["users"]

    tenant_keys = _get_tenant_keys(tenant)
    existing = users_col.find_one({
        "client_id": {"$in": tenant_keys},
        "email": str(body.email).lower(),
        "is_deleted": False,
    })

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "USER_ALREADY_EXISTS",
                    "message": f"A user with email '{body.email}' already exists for this tenant.",
                }
            },
        )

    # Process avatar upload to Firebase Storage if provided as base64
    avatar_url = body.avatar_url
    if body.avatar_base64:
        uploaded_url = _process_avatar_base64(
            body.avatar_base64,
            client_id=client_id,
            identifier=str(body.email).replace("@", "_").replace(".", "_"),
        )
        if uploaded_url:
            avatar_url = uploaded_url

    now_iso = datetime.now(timezone.utc).isoformat()
    new_user = {
        "client_id": client_id,
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
    "",
    summary="List all users for current tenant with search and status filters",
)
async def list_users(
    search: Optional[str] = Query(None, description="Search keyword matching name or email"),
    status: Optional[str] = Query(None, description="Filter by status (active, inactive, pending, all)"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    tenant: Dict[str, Any] = Depends(get_current_tenant),
):
    client_id = tenant["client_id"]
    db = get_db()
    users_col = db["users"]

    # Match tenant via all resolved tenant keys for hard isolation
    tenant_keys = _get_tenant_keys(tenant)
    query: Dict[str, Any] = {
        "client_id": {"$in": tenant_keys},
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
        "users": items,
        "total": total,
        "limit": limit,
        "skip": skip,
    }


@router.get(
    "/{user_id}",
    summary="Get single user by ID ensuring strict tenant isolation",
)
async def get_user(
    user_id: str,
    tenant: Dict[str, Any] = Depends(get_current_tenant),
):
    client_id = tenant["client_id"]
    db = get_db()
    users_col = db["users"]

    tenant_keys = _get_tenant_keys(tenant)
    id_filter = [user_id]
    if ObjectId.is_valid(user_id):
        id_filter.append(ObjectId(user_id))

    query = {
        "_id": {"$in": id_filter},
        "client_id": {"$in": tenant_keys},
        "is_deleted": False,
    }

    user = users_col.find_one(query)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "User does not exist or access was denied for this tenant.",
                }
            },
        )

    return _clean_doc(user)


@router.put(
    "/{user_id}",
    summary="Update tenant user by ID with optional profile picture update",
)
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    tenant: Dict[str, Any] = Depends(get_current_tenant),
):
    client_id = tenant["client_id"]
    db = get_db()
    users_col = db["users"]

    tenant_keys = _get_tenant_keys(tenant)
    id_filter = [user_id]
    if ObjectId.is_valid(user_id):
        id_filter.append(ObjectId(user_id))

    query = {
        "_id": {"$in": id_filter},
        "client_id": {"$in": tenant_keys},
        "is_deleted": False,
    }

    existing = users_col.find_one(query)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "User does not exist or access was denied for this tenant.",
                }
            },
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
        new_avatar_url = _process_avatar_base64(
            body.avatar_base64,
            client_id=client_id,
            identifier=user_id,
        )
        if new_avatar_url:
            updates["avatar_url"] = new_avatar_url
    elif body.avatar_url is not None:
        updates["avatar_url"] = body.avatar_url

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    users_col.update_one(query, {"$set": updates})
    updated = users_col.find_one(query)

    return _clean_doc(updated)


@router.delete(
    "/{user_id}",
    summary="Soft delete / deactivate user by ID",
)
async def delete_user(
    user_id: str,
    tenant: Dict[str, Any] = Depends(get_current_tenant),
):
    client_id = tenant["client_id"]
    db = get_db()
    users_col = db["users"]

    tenant_keys = _get_tenant_keys(tenant)
    id_filter = [user_id]
    if ObjectId.is_valid(user_id):
        id_filter.append(ObjectId(user_id))

    query = {
        "_id": {"$in": id_filter},
        "client_id": {"$in": tenant_keys},
        "is_deleted": False,
    }

    existing = users_col.find_one(query)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "User does not exist or access was denied for this tenant.",
                }
            },
        )

    now_iso = datetime.now(timezone.utc).isoformat()
    users_col.update_one(query, {
        "$set": {
            "is_deleted": True,
            "status": "inactive",
            "deleted_at": now_iso,
            "updated_at": now_iso,
        }
    })

    return {
        "message": "User deactivated successfully",
        "id": user_id,
        "deleted_at": now_iso,
    }
