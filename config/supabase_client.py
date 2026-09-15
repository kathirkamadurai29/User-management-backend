import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

env_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
if os.path.exists(env_file):
    load_dotenv(env_file)
else:
    load_dotenv()

supabase_url = os.getenv("SUPABASE_URL", "").strip()
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

_supabase_client = None
is_configured = False

FALLBACK_DIR = (
    os.environ.get("TMPDIR", "/tmp")
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
FALLBACK_CLIENTS_FILE = os.path.join(FALLBACK_DIR, ".clients_fallback.json")
FALLBACK_ADMINS_FILE = os.path.join(FALLBACK_DIR, ".admins_fallback.json")


def _read_json(filepath: str) -> List[Dict[str, Any]]:
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[Supabase Fallback] Error reading {filepath}: {e}")
    return []


def _write_json(filepath: str, data: List[Dict[str, Any]]) -> None:
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Supabase Fallback] Error writing {filepath}: {e}")


def _read_local_clients() -> List[Dict[str, Any]]:
    return _read_json(FALLBACK_CLIENTS_FILE)


def _write_local_clients(clients: List[Dict[str, Any]]) -> None:
    _write_json(FALLBACK_CLIENTS_FILE, clients)


def _read_local_admins() -> List[Dict[str, Any]]:
    return _read_json(FALLBACK_ADMINS_FILE)


def _write_local_admins(admins: List[Dict[str, Any]]) -> None:
    _write_json(FALLBACK_ADMINS_FILE, admins)


if supabase_url and supabase_key and supabase_url.startswith("http"):
    try:
        from supabase import create_client
        _supabase_client = create_client(supabase_url, supabase_key)
        is_configured = True
        print(f"[Supabase] Connected to {supabase_url}")
    except Exception as e:
        print(f"[Supabase] Connection warning: {e}. Using resilient fallback store.")
else:
    print("[Supabase] SUPABASE_URL / KEY not set. Operating in resilient store mode.")


# ==========================================
# CLIENTS (TENANTS) OPERATIONS
# ==========================================

async def insert_client_account(
    username: str,
    password_hash: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
) -> Dict[str, Any]:
    """Register client with username and password_hash only (no client_id/secret initially)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    client_uuid = str(uuid.uuid4())
    display_name = name.strip() if name else username.strip()

    new_client = {
        "id": client_uuid,
        "username": username.strip().lower(),
        "password_hash": password_hash,
        "client_id": None,
        "client_secret_hash": None,
        "name": display_name,
        "email": email.strip().lower() if email else None,
        "created_at": now_iso,
        "is_active": True,
    }

    # Attempt Supabase insert
    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("clients").insert({
                "username": new_client["username"],
                "password_hash": new_client["password_hash"],
                "name": new_client["name"],
                "email": new_client["email"],
                "is_active": True,
            }).execute()
            if res.data and len(res.data) > 0:
                record = res.data[0]
                # Sync into local store
                clients = _read_local_clients()
                clients = [c for c in clients if c.get("username") != record.get("username")]
                clients.append(record)
                _write_local_clients(clients)
                return record
        except Exception as e:
            print(f"[Supabase] Insert error ({e}), saving to resilient store.")

    # Local fallback
    clients = _read_local_clients()
    for c in clients:
        if c.get("username") == new_client["username"]:
            raise ValueError(f"Client username '{username}' already exists")
    clients.append(new_client)
    _write_local_clients(clients)

    return new_client


async def get_client_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve client by login username."""
    clean_username = username.strip().lower()
    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("clients").select("*").eq("username", clean_username).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception as e:
            print(f"[Supabase] Query error ({e}), falling back to local store.")

    clients = _read_local_clients()
    for c in clients:
        if (c.get("username") or "").lower() == clean_username:
            return c
    return None


async def get_client_by_client_id(client_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve client by generated API client_id (e.g. cli_...)."""
    clean_id = client_id.strip()
    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("clients").select("*").eq("client_id", clean_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception as e:
            print(f"[Supabase] Query error ({e}), falling back to local store.")

    clients = _read_local_clients()
    for c in clients:
        if c.get("client_id") == clean_id:
            return c
    return None


async def get_client_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieve client by UUID id, username, or client_id."""
    clean_id = identifier.strip()
    if is_configured and _supabase_client:
        try:
            # Check id
            res = _supabase_client.table("clients").select("*").eq("id", clean_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            # Check client_id
            res = _supabase_client.table("clients").select("*").eq("client_id", clean_id).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
            # Check username
            res = _supabase_client.table("clients").select("*").eq("username", clean_id.lower()).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception as e:
            print(f"[Supabase] Lookup error ({e}), falling back to local store.")

    clients = _read_local_clients()
    for c in clients:
        if (
            str(c.get("id")) == clean_id
            or c.get("client_id") == clean_id
            or (c.get("username") or "").lower() == clean_id.lower()
        ):
            return c
    return None


async def generate_and_store_client_credentials(
    client_identifier: str,
    client_id: str,
    client_secret_hash: str,
) -> Dict[str, Any]:
    """Store generated API credentials (client_id + client_secret_hash) ONCE for the client."""
    client = await get_client_by_identifier(client_identifier)
    if not client:
        raise ValueError("Client not found")

    if client.get("client_id") and client.get("client_secret_hash"):
        raise ValueError("API credentials have already been generated for this client.")

    updates = {
        "client_id": client_id,
        "client_secret_hash": client_secret_hash,
    }

    if is_configured and _supabase_client:
        try:
            query = _supabase_client.table("clients").update(updates)
            if client.get("id"):
                res = query.eq("id", client["id"]).execute()
            elif client.get("username"):
                res = query.eq("username", client["username"]).execute()
            else:
                res = None
            if res and res.data and len(res.data) > 0:
                updated_record = res.data[0]
                # Sync into local store
                clients = _read_local_clients()
                for i, c in enumerate(clients):
                    if c.get("id") == client.get("id") or c.get("username") == client.get("username"):
                        clients[i].update(updates)
                _write_local_clients(clients)
                return updated_record
        except Exception as e:
            print(f"[Supabase] Update credentials error ({e}), storing in resilient store.")

    clients = _read_local_clients()
    for c in clients:
        if c.get("id") == client.get("id") or c.get("username") == client.get("username"):
            c.update(updates)
            _write_local_clients(clients)
            return c

    client.update(updates)
    clients.append(client)
    _write_local_clients(clients)
    return client


async def list_all_clients() -> List[Dict[str, Any]]:
    """List all registered clients (used by Super Admin), merging remote and resilient local store."""
    remote_clients = []
    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("clients").select("*").order("created_at", desc=True).execute()
            if res.data is not None:
                remote_clients = res.data
        except Exception as e:
            print(f"[Supabase] List clients error ({e}), reading from resilient store.")

    local_clients = _read_local_clients()

    # Merge remote and local stores seamlessly
    merged_map = {}
    for c in remote_clients:
        k = c.get("id") or c.get("username") or c.get("client_id")
        if k:
            merged_map[k] = dict(c)

    for c in local_clients:
        k = c.get("id") or c.get("username") or c.get("client_id")
        if k:
            if k in merged_map:
                merged_map[k].update(c)
            else:
                merged_map[k] = dict(c)

    results = list(merged_map.values())
    for r in results:
        if not r.get("username"):
            r["username"] = r.get("client_id") or (r.get("name", "client") or "client").lower().replace(" ", "_")

    return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)


async def update_client_status(client_identifier: str, is_active: bool) -> Optional[Dict[str, Any]]:
    """Activate or deactivate a client account."""
    client = await get_client_by_identifier(client_identifier)
    if not client:
        return None

    if is_configured and _supabase_client:
        try:
            query = _supabase_client.table("clients").update({"is_active": is_active})
            if client.get("id"):
                res = query.eq("id", client["id"]).execute()
            elif client.get("client_id"):
                res = query.eq("client_id", client["client_id"]).execute()
            else:
                res = query.eq("username", client.get("username")).execute()
            if res and res.data:
                return res.data[0]
        except Exception as e:
            print(f"[Supabase] Update status error: {e}")

    clients = _read_local_clients()
    for c in clients:
        if (
            str(c.get("id")) == client_identifier
            or c.get("client_id") == client_identifier
            or (c.get("username") or "").lower() == client_identifier.lower()
        ):
            c["is_active"] = is_active
            _write_local_clients(clients)
            return c
    return None


async def delete_client_account(client_identifier: str) -> bool:
    """Delete a client account."""
    client = await get_client_by_identifier(client_identifier)
    if not client:
        return False

    if is_configured and _supabase_client:
        try:
            query = _supabase_client.table("clients").delete()
            if client.get("id"):
                query.eq("id", client["id"]).execute()
            elif client.get("client_id"):
                query.eq("client_id", client["client_id"]).execute()
            else:
                query.eq("username", client.get("username")).execute()
        except Exception as e:
            print(f"[Supabase] Delete client error: {e}")

    clients = _read_local_clients()
    filtered = [
        c for c in clients
        if str(c.get("id")) != client_identifier
        and c.get("client_id") != client_identifier
        and (c.get("username") or "").lower() != client_identifier.lower()
    ]
    _write_local_clients(filtered)
    return True


# ==========================================
# SUPER ADMIN OPERATIONS
# ==========================================

async def insert_admin(username: str, password_hash: str, role: str = "super_admin") -> Dict[str, Any]:
    """Seed or insert a super admin."""
    now_iso = datetime.now(timezone.utc).isoformat()
    admin_uuid = str(uuid.uuid4())
    admin_record = {
        "id": admin_uuid,
        "username": username.strip().lower(),
        "password_hash": password_hash,
        "role": role,
        "created_at": now_iso,
    }

    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("admins").insert({
                "username": admin_record["username"],
                "password_hash": admin_record["password_hash"],
                "role": admin_record["role"],
            }).execute()
            if res.data and len(res.data) > 0:
                record = res.data[0]
                admins = _read_local_admins()
                admins = [a for a in admins if a.get("username") != record.get("username")]
                admins.append(record)
                _write_local_admins(admins)
                return record
        except Exception as e:
            print(f"[Supabase] Insert admin error ({e}), saving to resilient store.")

    admins = _read_local_admins()
    for a in admins:
        if a.get("username") == admin_record["username"]:
            raise ValueError(f"Admin '{username}' already exists")
    admins.append(admin_record)
    _write_local_admins(admins)
    return admin_record


async def get_admin_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Retrieve super admin by username."""
    clean_username = username.strip().lower()
    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("admins").select("*").eq("username", clean_username).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception as e:
            print(f"[Supabase] Query admin error ({e}), falling back to local store.")

    admins = _read_local_admins()
    for a in admins:
        if (a.get("username") or "").lower() == clean_username:
            return a
    return None


async def list_all_admins() -> List[Dict[str, Any]]:
    """List all super admins, merging remote and local store."""
    remote_admins = []
    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("admins").select("*").execute()
            if res.data is not None:
                remote_admins = res.data
        except Exception as e:
            print(f"[Supabase] List admins error: {e}")

    local_admins = _read_local_admins()
    merged = {a.get("username"): a for a in remote_admins if a.get("username")}
    for a in local_admins:
        if a.get("username") and a["username"] not in merged:
            merged[a["username"]] = a

    return list(merged.values())


# Backward compatibility helper
async def insert_client(client_id: str, client_secret_hash: str, name: str, email: Optional[str] = None) -> Dict[str, Any]:
    new_client = {
        "client_id": client_id,
        "client_secret_hash": client_secret_hash,
        "name": name,
        "email": email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True,
    }
    if is_configured and _supabase_client:
        try:
            res = _supabase_client.table("clients").insert(new_client).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            print(f"[Supabase] Legacy insert error: {e}")

    clients = _read_local_clients()
    clients.append(new_client)
    _write_local_clients(clients)
    return new_client
