import os
import sys
import uuid
from starlette.testclient import TestClient

# Ensure backend path is on sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from main import app
from seed_admin import seed_super_admin
import asyncio


def run_tests():
    print("\n=======================================================")
    print("  MULTI-TENANT USER PLATFORM: FULL INTEGRATION TESTS   ")
    print("=======================================================\n")

    client = TestClient(app)
    unique_suffix = uuid.uuid4().hex[:6]
    username_a = f"tenant_a_{unique_suffix}"
    password_a = "SecretPass123!"
    username_b = f"tenant_b_{unique_suffix}"
    password_b = "SecretPass456!"

    # -------------------------------------------------------------
    # TEST 1: Register Tenant A with username + password only
    # -------------------------------------------------------------
    print("1. Testing POST /api/v1/auth/register (Client sign up with username + password)...")
    res_reg_a = client.post("/api/v1/auth/register", json={
        "username": username_a,
        "password": password_a,
        "name": f"Tenant Alpha {unique_suffix}",
        "email": f"alpha_{unique_suffix}@corp.com",
    })
    assert res_reg_a.status_code == 201, f"Register A failed: {res_reg_a.text}"
    data_reg_a = res_reg_a.json()
    assert data_reg_a["username"] == username_a
    assert "client_id" not in data_reg_a and "client_secret" not in data_reg_a, "Registration must NOT return client_id/secret yet"
    print(f"   [OK] Registered client '{username_a}' without external API credentials.")

    # -------------------------------------------------------------
    # TEST 2: Duplicate username validation
    # -------------------------------------------------------------
    print("\n2. Testing duplicate username conflict...")
    res_dup = client.post("/api/v1/auth/register", json={
        "username": username_a,
        "password": password_a,
    })
    assert res_dup.status_code == 409, f"Expected 409, got {res_dup.status_code}"
    print("   [OK] Duplicate username correctly rejected with HTTP 409.")

    # -------------------------------------------------------------
    # TEST 3: Client Login with username + password (Session JWT)
    # -------------------------------------------------------------
    print("\n3. Testing POST /api/v1/auth/login (Obtain Session JWT for Dashboard)...")
    res_login_a = client.post("/api/v1/auth/login", json={
        "username": username_a,
        "password": password_a,
    })
    assert res_login_a.status_code == 200, f"Login failed: {res_login_a.text}"
    data_login_a = res_login_a.json()
    session_token_a = data_login_a["access_token"]
    assert session_token_a, "Missing access_token"
    assert data_login_a["client"]["username"] == username_a
    headers_session_a = {"Authorization": f"Bearer {session_token_a}"}
    print(f"   [OK] Session JWT obtained for '{username_a}'.")

    # -------------------------------------------------------------
    # TEST 4: Invalid login credentials rejection
    # -------------------------------------------------------------
    print("\n4. Testing invalid login password...")
    res_bad_login = client.post("/api/v1/auth/login", json={
        "username": username_a,
        "password": "WrongPassword!",
    })
    assert res_bad_login.status_code == 401
    print("   [OK] Invalid password correctly rejected with HTTP 401.")

    # -------------------------------------------------------------
    # TEST 5: One-Time API Credentials Generation
    # -------------------------------------------------------------
    print("\n5. Testing POST /api/v1/clients/credentials (Generate client_id + client_secret ONCE)...")
    res_creds_a = client.post("/api/v1/clients/credentials", headers=headers_session_a)
    assert res_creds_a.status_code == 201, f"Credentials generation failed: {res_creds_a.text}"
    data_creds_a = res_creds_a.json()
    assert data_creds_a["client_id"].startswith("cli_"), "Invalid client_id format"
    assert data_creds_a["client_secret"].startswith("sec_"), "Invalid client_secret format"
    client_id_a = data_creds_a["client_id"]
    client_secret_a = data_creds_a["client_secret"]
    print(f"   [OK] Generated external credentials: {client_id_a}")

    # -------------------------------------------------------------
    # TEST 6: Prevent Re-Generation of API Credentials
    # -------------------------------------------------------------
    print("\n6. Testing re-generation prevention on POST /api/v1/clients/credentials...")
    res_creds_dup = client.post("/api/v1/clients/credentials", headers=headers_session_a)
    assert res_creds_dup.status_code == 409, f"Expected 409 Conflict on repeated generation, got {res_creds_dup.status_code}"
    print("   [OK] Re-generation correctly blocked with HTTP 409.")

    # -------------------------------------------------------------
    # TEST 7: External API Token Exchange (API JWT)
    # -------------------------------------------------------------
    print("\n7. Testing POST /api/v1/auth/token (External consumer exchanges client_id + secret)...")
    res_api_token = client.post("/api/v1/auth/token", json={
        "client_id": client_id_a,
        "client_secret": client_secret_a,
    })
    assert res_api_token.status_code == 200, f"API token exchange failed: {res_api_token.text}"
    data_api_token = res_api_token.json()
    api_jwt_a = data_api_token["access_token"]
    headers_api_a = {"Authorization": f"Bearer {api_jwt_a}"}
    print(f"   [OK] API JWT issued for outside API consumer: {data_api_token['client_id']}.")

    # -------------------------------------------------------------
    # TEST 8: Create User with Profile Picture (Firebase Storage)
    # -------------------------------------------------------------
    print("\n8. Testing POST /api/v1/users (User creation with avatar upload)...")
    fake_avatar_b64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    res_user = client.post("/api/v1/users", headers=headers_session_a, json={
        "name": "Ellen Ripley",
        "email": f"ripley_{unique_suffix}@weyland.corp",
        "role": "admin",
        "status": "active",
        "avatar_base64": fake_avatar_b64,
    })
    assert res_user.status_code == 201, f"User creation failed: {res_user.text}"
    user_data = res_user.json()
    user_id = user_data["_id"]
    assert user_data["avatar_url"], "avatar_url should be populated from Firebase Storage pipeline"
    print(f"   [OK] Created user: {user_data['name']} (ID: {user_id})")
    print(f"   [OK] Avatar URL saved: {user_data['avatar_url'][:60]}...")

    # -------------------------------------------------------------
    # TEST 9: List Users with Search and Status Filter
    # -------------------------------------------------------------
    print("\n9. Testing GET /api/v1/users with filters...")
    res_list = client.get("/api/v1/users?search=ripley", headers=headers_session_a)
    assert res_list.status_code == 200
    assert len(res_list.json()["users"]) >= 1
    print("   [OK] User listing and search filter verified.")

    # -------------------------------------------------------------
    # TEST 10: Multi-Tenant Hard Isolation
    # -------------------------------------------------------------
    print("\n10. Testing Hard Multi-Tenant Isolation (Tenant B vs Tenant A)...")
    # Register & login Tenant B
    client.post("/api/v1/auth/register", json={
        "username": username_b,
        "password": password_b,
        "name": f"Tenant Beta {unique_suffix}",
    })
    token_b = client.post("/api/v1/auth/login", json={
        "username": username_b,
        "password": password_b,
    }).json()["access_token"]
    headers_session_b = {"Authorization": f"Bearer {token_b}"}

    # Attempt cross-tenant access to Tenant A user
    res_cross = client.get(f"/api/v1/users/{user_id}", headers=headers_session_b)
    assert res_cross.status_code == 404, f"Security breach! Expected 404, got {res_cross.status_code}"
    print("   [OK] Hard isolation verified: Tenant B receives HTTP 404 when querying Tenant A user.")

    # -------------------------------------------------------------
    # TEST 11: Seed and Authenticate Super Admin
    # -------------------------------------------------------------
    print("\n11. Testing Super Admin Seeding and Login...")
    admin_user = f"admin_{unique_suffix}"
    admin_pass = "SuperAdminSecret999!"
    asyncio.run(seed_super_admin(admin_user, admin_pass))

    res_admin_login = client.post("/api/v1/admin/auth/login", json={
        "username": admin_user,
        "password": admin_pass,
    })
    assert res_admin_login.status_code == 200, f"Admin login failed: {res_admin_login.text}"
    admin_token = res_admin_login.json()["access_token"]
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    print(f"   [OK] Super Admin authenticated: role = {res_admin_login.json()['role']}")

    # -------------------------------------------------------------
    # TEST 12: Super Admin Bypasses Tenant Isolation (List all clients)
    # -------------------------------------------------------------
    print("\n12. Testing GET /api/v1/admin/clients (Super Admin lists all tenants)...")
    res_all_clients = client.get("/api/v1/admin/clients", headers=headers_admin)
    assert res_all_clients.status_code == 200
    all_clients = res_all_clients.json()["clients"]
    assert any(c.get("username") == username_a for c in all_clients)
    assert any(c.get("username") == username_b for c in all_clients)
    print(f"   [OK] Super Admin successfully listed {len(all_clients)} registered clients across platform.")

    # -------------------------------------------------------------
    # TEST 13: Super Admin drills into Tenant A users & CRUD
    # -------------------------------------------------------------
    print("\n13. Testing Super Admin drill-down into Tenant A users...")
    res_drill = client.get(f"/api/v1/admin/clients/{username_a}/users", headers=headers_admin)
    assert res_drill.status_code == 200
    assert len(res_drill.json()["users"]) >= 1
    print(f"   [OK] Admin drilled into Tenant A user directory: {len(res_drill.json()['users'])} user(s) found.")

    # Admin creates user for Tenant A
    print("\n14. Testing Admin creates user for Tenant A...")
    res_admin_create_user = client.post(f"/api/v1/admin/clients/{username_a}/users", headers=headers_admin, json={
        "name": "Bishop Android",
        "email": f"bishop_{unique_suffix}@weyland.corp",
        "role": "viewer",
        "status": "active",
    })
    assert res_admin_create_user.status_code == 201
    admin_created_user_id = res_admin_create_user.json()["_id"]
    print(f"   [OK] Admin provisioned user '{res_admin_create_user.json()['name']}' for Tenant A.")

    # Admin updates user
    res_admin_update = client.put(
        f"/api/v1/admin/clients/{username_a}/users/{admin_created_user_id}",
        headers=headers_admin,
        json={"name": "Bishop Synthetic Model 341-B"},
    )
    assert res_admin_update.status_code == 200
    print(f"   [OK] Admin updated user name to: {res_admin_update.json()['name']}.")

    # Admin soft-deletes user
    res_admin_del = client.delete(
        f"/api/v1/admin/clients/{username_a}/users/{admin_created_user_id}",
        headers=headers_admin,
    )
    assert res_admin_del.status_code == 200
    print("   [OK] Admin deactivated user.")

    # -------------------------------------------------------------
    # TEST 14: Super Admin Platform-Wide Activity Telemetry
    # -------------------------------------------------------------
    print("\n15. Testing GET /api/v1/admin/activity (Platform-wide telemetry)...")
    res_admin_act = client.get("/api/v1/admin/activity", headers=headers_admin)
    assert res_admin_act.status_code == 200
    telemetry = res_admin_act.json()
    assert "metrics" in telemetry and "logs" in telemetry
    print(f"   [OK] Platform telemetry recorded {telemetry['metrics']['total_requests']} total requests.")
    print(f"   [OK] Active tenants monitored: {telemetry['metrics']['active_tenants_count']}")

    # -------------------------------------------------------------
    # TEST 15: Swagger UI Live Documentation
    # -------------------------------------------------------------
    print("\n16. Testing Swagger Docs at /api-docs...")
    res_docs = client.get("/api-docs")
    assert res_docs.status_code == 200
    print("   [OK] OpenAPI / Swagger documentation is online (HTTP 200).")

    print("\n=======================================================")
    print("  ALL 16 INTEGRATION TEST SUITES PASSED SUCCESSFULLY!  ")
    print("=======================================================\n")


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\n[FATAL ERROR] Integration test failure: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
