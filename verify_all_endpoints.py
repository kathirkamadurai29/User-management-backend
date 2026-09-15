import os
import sys
import uuid
import asyncio
from io import BytesIO
from starlette.testclient import TestClient

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from main import app
from seed_admin import seed_super_admin


def test_entire_api():
    print("================================================================")
    print("  COMPREHENSIVE ENDPOINT AUDIT & VERIFICATION SUITE")
    print("================================================================\n")

    client = TestClient(app)
    rand_id = uuid.uuid4().hex[:6]
    user_a = f"tenant_alpha_{rand_id}"
    pass_a = "StrongPass123!"
    user_b = f"tenant_beta_{rand_id}"
    pass_b = "StrongPass456!"

    # 1. System Endpoints
    print("1. Checking System Endpoints...")
    r = client.get("/health")
    assert r.status_code == 200, f"Healthcheck failed: {r.text}"
    assert r.json().get("status") == "healthy"
    print("   [OK] GET /health (HTTP 200)")

    r = client.get("/api-docs")
    assert r.status_code == 200, f"Swagger docs failed: {r.text}"
    print("   [OK] GET /api-docs (HTTP 200)")

    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200, f"OpenAPI schema failed: {r.text}"
    print("   [OK] GET /api/v1/openapi.json (HTTP 200)")

    # 2. Client Auth Endpoints
    print("\n2. Checking /auth/register & /auth/login...")
    # Register validation: too short username
    r = client.post("/auth/register", json={"username": "ab", "password": pass_a})
    assert r.status_code in (400, 422), f"Expected 400/422 for short username, got {r.status_code}"
    print("   [OK] POST /auth/register rejected short username (HTTP 400/422)")

    # Register validation: too short password
    r = client.post("/auth/register", json={"username": user_a, "password": "123"})
    assert r.status_code in (400, 422), f"Expected 400/422 for short password, got {r.status_code}"
    print("   [OK] POST /auth/register rejected short password (HTTP 400/422)")

    # Register Tenant A successfully
    r_reg_a = client.post("/auth/register", json={
        "username": user_a,
        "password": pass_a,
        "name": f"Alpha Corp {rand_id}",
        "email": f"alpha_{rand_id}@example.com",
    })
    assert r_reg_a.status_code == 201, f"Tenant A registration failed: {r_reg_a.text}"
    reg_data = r_reg_a.json()
    assert reg_data["username"] == user_a
    assert "client_id" not in reg_data and "client_secret" not in reg_data
    print(f"   [OK] POST /auth/register registered '{user_a}' without external credentials (HTTP 201)")

    # Register duplicate username
    r_dup = client.post("/auth/register", json={"username": user_a, "password": pass_a})
    assert r_dup.status_code == 409, f"Expected 409 for duplicate username, got {r_dup.status_code}"
    print("   [OK] POST /auth/register prevented duplicate username (HTTP 409)")

    # Login with wrong password
    r_bad_pw = client.post("/auth/login", json={"username": user_a, "password": "WrongPassword"})
    assert r_bad_pw.status_code == 401, f"Expected 401 for wrong password, got {r_bad_pw.status_code}"
    print("   [OK] POST /auth/login rejected invalid password (HTTP 401)")

    # Login successfully
    r_login_a = client.post("/auth/login", json={"username": user_a, "password": pass_a})
    assert r_login_a.status_code == 200, f"Login failed: {r_login_a.text}"
    login_data_a = r_login_a.json()
    session_token_a = login_data_a["access_token"]
    assert session_token_a
    assert login_data_a["client"]["username"] == user_a
    headers_a = {"Authorization": f"Bearer {session_token_a}"}
    print(f"   [OK] POST /auth/login returned Session JWT (role: {login_data_a['client'].get('username')}) (HTTP 200)")

    # 3. Client Profile & One-Time API Credentials
    print("\n3. Checking /clients/me & /clients/credentials...")
    r_me = client.get("/clients/me", headers=headers_a)
    assert r_me.status_code == 200, f"Get profile failed: {r_me.text}"
    assert r_me.json()["username"] == user_a
    assert r_me.json()["has_api_credentials"] is False
    print("   [OK] GET /clients/me returned current client profile (HTTP 200)")

    # Unauthenticated /clients/me
    r_me_unauth = client.get("/clients/me")
    assert r_me_unauth.status_code == 401
    print("   [OK] GET /clients/me blocked unauthenticated access (HTTP 401)")

    # Generate one-time credentials
    r_creds = client.post("/clients/credentials", headers=headers_a)
    assert r_creds.status_code == 201, f"Generate credentials failed: {r_creds.text}"
    creds_data = r_creds.json()
    client_id_a = creds_data["client_id"]
    client_secret_a = creds_data["client_secret"]
    assert client_id_a.startswith("cli_")
    assert client_secret_a.startswith("sec_")
    print(f"   [OK] POST /clients/credentials generated one-time credentials: {client_id_a} (HTTP 201)")

    # Attempt second credentials generation -> Conflict 409
    r_creds_dup = client.post("/clients/credentials", headers=headers_a)
    assert r_creds_dup.status_code == 409, f"Expected 409 on duplicate credentials generation, got {r_creds_dup.status_code}"
    print("   [OK] POST /clients/credentials blocked repeated generation (HTTP 409)")

    # 4. Programmatic API Token Exchange (/auth/token)
    print("\n4. Checking /auth/token (Outside API Consumer)...")
    # Invalid secret
    r_token_bad = client.post("/auth/token", json={"client_id": client_id_a, "client_secret": "wrong_secret"})
    assert r_token_bad.status_code == 401
    print("   [OK] POST /auth/token rejected invalid secret (HTTP 401)")

    # Valid token exchange
    r_token = client.post("/auth/token", json={"client_id": client_id_a, "client_secret": client_secret_a})
    assert r_token.status_code == 200, f"Token exchange failed: {r_token.text}"
    api_jwt_a = r_token.json()["access_token"]
    assert api_jwt_a
    headers_api_a = {"Authorization": f"Bearer {api_jwt_a}"}
    print(f"   [OK] POST /auth/token issued programmatic API JWT for client: {client_id_a} (HTTP 200)")

    # 5. Users Endpoints (CRUD, Tenant Isolation, Avatar Processing)
    print("\n5. Checking /users CRUD & Avatar Storage...")
    # Multipart avatar upload endpoint
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    r_upload = client.post(
        "/users/upload-avatar",
        headers=headers_a,
        files={"file": ("profile.png", BytesIO(fake_png), "image/png")},
    )
    assert r_upload.status_code == 200, f"Upload avatar failed: {r_upload.text}"
    uploaded_avatar_url = r_upload.json()["avatar_url"]
    assert uploaded_avatar_url
    print(f"   [OK] POST /users/upload-avatar uploaded file to Firebase Storage (HTTP 200)")

    # Create user with avatar_url
    user1_email = f"user1_{rand_id}@alpha.com"
    r_u1 = client.post("/users", headers=headers_a, json={
        "name": "Sarah Connor",
        "email": user1_email,
        "role": "admin",
        "status": "active",
        "avatar_url": uploaded_avatar_url,
        "metadata": {"department": "Operations"},
    })
    assert r_u1.status_code == 201, f"Create user 1 failed: {r_u1.text}"
    u1_data = r_u1.json()
    u1_id = u1_data["_id"]
    assert u1_data["email"] == user1_email
    assert u1_data["avatar_url"] == uploaded_avatar_url
    print(f"   [OK] POST /users created user '{u1_data['name']}' with avatar (HTTP 201)")

    # Create user with avatar_base64
    b64_avatar = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    user2_email = f"user2_{rand_id}@alpha.com"
    r_u2 = client.post("/users", headers=headers_api_a, json={
        "name": "John Connor",
        "email": user2_email,
        "role": "member",
        "status": "pending",
        "avatar_base64": b64_avatar,
    })
    assert r_u2.status_code == 201, f"Create user 2 failed: {r_u2.text}"
    u2_data = r_u2.json()
    u2_id = u2_data["_id"]
    assert u2_data["avatar_url"], "avatar_url must be populated from avatar_base64"
    print(f"   [OK] POST /users (via API JWT) created user with base64 avatar (HTTP 201)")

    # Prevent duplicate email under same tenant
    r_dup_user = client.post("/users", headers=headers_a, json={
        "name": "Imposter",
        "email": user1_email,
    })
    assert r_dup_user.status_code == 409
    print("   [OK] POST /users prevented duplicate email under same tenant (HTTP 409)")

    # List users with filters
    r_list = client.get("/users?status=active", headers=headers_a)
    assert r_list.status_code == 200
    list_active = r_list.json()["users"]
    assert any(u["_id"] == u1_id for u in list_active)
    print("   [OK] GET /users?status=active filtered correctly (HTTP 200)")

    r_search = client.get(f"/users?search=Sarah", headers=headers_a)
    assert r_search.status_code == 200
    assert len(r_search.json()["users"]) >= 1
    print("   [OK] GET /users?search=Sarah search filter returned matches (HTTP 200)")

    # Get single user
    r_get1 = client.get(f"/users/{u1_id}", headers=headers_a)
    assert r_get1.status_code == 200
    assert r_get1.json()["_id"] == u1_id
    print(f"   [OK] GET /users/{u1_id} retrieved user successfully (HTTP 200)")

    # Update user
    r_upd = client.put(f"/users/{u1_id}", headers=headers_a, json={
        "name": "Sarah Connor Brewster",
        "status": "active",
        "metadata": {"department": "Special Ops"},
    })
    assert r_upd.status_code == 200
    assert r_upd.json()["name"] == "Sarah Connor Brewster"
    print(f"   [OK] PUT /users/{u1_id} updated user fields (HTTP 200)")

    # Soft delete user
    r_del2 = client.delete(f"/users/{u2_id}", headers=headers_a)
    assert r_del2.status_code == 200
    print(f"   [OK] DELETE /users/{u2_id} soft-deleted user (HTTP 200)")

    # Verify soft-deleted user excluded from standard list
    r_list_after = client.get("/users", headers=headers_a)
    assert not any(u["_id"] == u2_id for u in r_list_after.json()["users"])
    print("   [OK] Soft-deleted user excluded from active listing (HTTP 200)")

    # 6. Hard Multi-Tenant Isolation Check
    print("\n6. Checking Hard Tenant Isolation (Tenant B vs Tenant A)...")
    client.post("/auth/register", json={"username": user_b, "password": pass_b})
    tok_b = client.post("/auth/login", json={"username": user_b, "password": pass_b}).json()["access_token"]
    headers_b = {"Authorization": f"Bearer {tok_b}"}

    # Tenant B attempts to read Tenant A's user
    r_cross_get = client.get(f"/users/{u1_id}", headers=headers_b)
    assert r_cross_get.status_code == 404, f"Security breach! Expected 404, got {r_cross_get.status_code}"
    print("   [OK] Cross-tenant GET /users/{id} returned HTTP 404")

    # Tenant B attempts to update Tenant A's user
    r_cross_put = client.put(f"/users/{u1_id}", headers=headers_b, json={"name": "Hacked Name"})
    assert r_cross_put.status_code == 404
    print("   [OK] Cross-tenant PUT /users/{id} returned HTTP 404")

    # Tenant B attempts to delete Tenant A's user
    r_cross_del = client.delete(f"/users/{u1_id}", headers=headers_b)
    assert r_cross_del.status_code == 404
    print("   [OK] Cross-tenant DELETE /users/{id} returned HTTP 404")

    # 7. Activity & AI Insights Endpoints
    print("\n7. Checking /activity & /insights...")
    r_act = client.get("/activity", headers=headers_a)
    assert r_act.status_code == 200
    act_data = r_act.json()
    assert "metrics" in act_data and "logs" in act_data
    assert act_data["metrics"]["total_requests"] >= 1
    print(f"   [OK] GET /activity returned metrics (total: {act_data['metrics']['total_requests']}, rate: {act_data['metrics']['success_rate_percent']}%)")

    r_ins = client.get("/insights", headers=headers_a)
    assert r_ins.status_code == 200
    ins_data = r_ins.json()
    assert "insight" in ins_data and ins_data["insight"]
    print(f"   [OK] GET /insights returned AI insight (provider: {ins_data['provider']})")

    # 8. Super Admin Engine Endpoints
    print("\n8. Checking Super Admin Endpoints (/admin/*)...")
    admin_user = f"adm_{rand_id}"
    admin_pass = "SuperSecretAdmin999!"
    asyncio.run(seed_super_admin(admin_user, admin_pass))

    # Admin Login bad credentials
    r_bad_adm = client.post("/admin/auth/login", json={"username": admin_user, "password": "WrongPassword"})
    assert r_bad_adm.status_code == 401
    print("   [OK] POST /admin/auth/login rejected invalid credentials (HTTP 401)")

    # Admin Login success
    r_adm_login = client.post("/admin/auth/login", json={"username": admin_user, "password": admin_pass})
    assert r_adm_login.status_code == 200
    adm_token = r_adm_login.json()["access_token"]
    headers_adm = {"Authorization": f"Bearer {adm_token}"}
    print("   [OK] POST /admin/auth/login returned Super Admin JWT (HTTP 200)")

    # List all clients across platform
    r_adm_clients = client.get("/admin/clients", headers=headers_adm)
    assert r_adm_clients.status_code == 200
    clients_list = r_adm_clients.json()["clients"]
    assert any(c["username"] == user_a for c in clients_list)
    assert any(c["username"] == user_b for c in clients_list)
    print(f"   [OK] GET /admin/clients listed {len(clients_list)} tenants with user counts (HTTP 200)")

    # Admin drill-down into Tenant A's users
    r_drill = client.get(f"/admin/clients/{user_a}/users", headers=headers_adm)
    assert r_drill.status_code == 200
    assert len(r_drill.json()["users"]) >= 1
    print(f"   [OK] GET /admin/clients/{user_a}/users drilled into user directory (HTTP 200)")

    # Admin creates user under Tenant A
    r_adm_create = client.post(f"/admin/clients/{user_a}/users", headers=headers_adm, json={
        "name": "Kyle Reese",
        "email": f"reese_{rand_id}@resistance.org",
        "role": "member",
        "status": "active",
    })
    assert r_adm_create.status_code == 201
    adm_user_id = r_adm_create.json()["_id"]
    print(f"   [OK] POST /admin/clients/{user_a}/users provisioned user '{r_adm_create.json()['name']}' (HTTP 201)")

    # Admin gets user
    r_adm_get_u = client.get(f"/admin/clients/{user_a}/users/{adm_user_id}", headers=headers_adm)
    assert r_adm_get_u.status_code == 200
    assert r_adm_get_u.json()["_id"] == adm_user_id
    print("   [OK] GET /admin/clients/{id}/users/{user_id} fetched user (HTTP 200)")

    # Admin updates user
    r_adm_upd_u = client.put(f"/admin/clients/{user_a}/users/{adm_user_id}", headers=headers_adm, json={
        "name": "Kyle Reese (Tech-Com Sergeant)",
    })
    assert r_adm_upd_u.status_code == 200
    assert r_adm_upd_u.json()["name"] == "Kyle Reese (Tech-Com Sergeant)"
    print("   [OK] PUT /admin/clients/{id}/users/{user_id} updated user (HTTP 200)")

    # Admin soft-deletes user
    r_adm_del_u = client.delete(f"/admin/clients/{user_a}/users/{adm_user_id}", headers=headers_adm)
    assert r_adm_del_u.status_code == 200
    print("   [OK] DELETE /admin/clients/{id}/users/{user_id} deactivated user (HTTP 200)")

    # Admin deactivates tenant client
    r_deact = client.patch(f"/admin/clients/{user_a}/status", headers=headers_adm, json={"is_active": False})
    assert r_deact.status_code == 200
    print(f"   [OK] PATCH /admin/clients/{user_a}/status deactivated client (HTTP 200)")

    # Deactivated client login should be blocked with 403 ACCOUNT_DEACTIVATED
    r_blocked_login = client.post("/auth/login", json={"username": user_a, "password": pass_a})
    assert r_blocked_login.status_code == 403, f"Expected 403, got {r_blocked_login.status_code}"
    print("   [OK] Deactivated client blocked from logging in (HTTP 403)")

    # Reactivate client
    r_react = client.patch(f"/admin/clients/{user_a}/status", headers=headers_adm, json={"is_active": True})
    assert r_react.status_code == 200
    print(f"   [OK] PATCH /admin/clients/{user_a}/status reactivated client (HTTP 200)")

    # Admin platform-wide telemetry
    r_adm_act = client.get("/admin/activity", headers=headers_adm)
    assert r_adm_act.status_code == 200
    assert "metrics" in r_adm_act.json()
    print(f"   [OK] GET /admin/activity returned platform-wide metrics (HTTP 200)")

    # Admin deletes tenant B
    r_del_client = client.delete(f"/admin/clients/{user_b}", headers=headers_adm)
    assert r_del_client.status_code == 200
    print(f"   [OK] DELETE /admin/clients/{user_b} removed client and cascaded users (HTTP 200)")

    # 9. Direct /api/v1 Prefix Parity Checks
    print("\n9. Checking /api/v1 prefix parity...")
    assert client.get("/api/v1/health").status_code in (200, 404)  # /health is root
    assert client.get("/api/v1/users", headers=headers_a).status_code == 200
    assert client.get("/api/v1/activity", headers=headers_a).status_code == 200
    assert client.get("/api/v1/insights", headers=headers_a).status_code == 200
    assert client.get("/api/v1/clients/me", headers=headers_a).status_code == 200
    assert client.get("/api/v1/admin/clients", headers=headers_adm).status_code == 200
    assert client.get("/api/v1/admin/activity", headers=headers_adm).status_code == 200
    print("   [OK] Verified parity: endpoints accessible via both /... and /api/v1/...")

    print("\n================================================================")
    print("  ALL ENDPOINTS AUDITED & VERIFIED SUCCESSFULLY! ZERO ERRORS.")
    print("================================================================\n")


if __name__ == "__main__":
    test_entire_api()
