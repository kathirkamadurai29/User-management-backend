# Multi-Tenant User Management Platform — Backend Service & Super Admin Engine

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_2.0-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11_|_3.14-3776AB?logo=python)](https://python.org)
[![Node.js](https://img.shields.io/badge/Node.js-Express_4.21-339933?logo=node.js)](https://nodejs.org)
[![MongoDB](https://img.shields.io/badge/Database-MongoDB_Atlas-47A248?logo=mongodb)](https://www.mongodb.com)
[![Supabase](https://img.shields.io/badge/Auth_DB-Supabase_(PostgreSQL)-3ECF8E?logo=supabase)](https://supabase.com)
[![Firebase](https://img.shields.io/badge/Storage-Firebase_Storage-FFCA28?logo=firebase)](https://firebase.google.com)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render)](https://render.com)

Production-ready multi-tenant user management REST API featuring dual-track authentication (Dashboard Session JWT vs. External Consumer API JWT), Super Admin platform portal, isolated MongoDB user directories, Firebase Storage for user profile pictures, and turnkey deployment targets.

---

## 🌐 Live Deployment URLs

| Service | Target Platform | Live URL |
| :--- | :--- | :--- |
| **Backend REST API** | **Render** | `https://user-management-backend-xxxx.onrender.com` |
| **Frontend Client Dashboard** | **Vercel** | `https://user-management-frontend-xxxx.vercel.app` |
| **Interactive API Documentation** | **Swagger UI** | `https://user-management-backend-xxxx.onrender.com/api-docs` |
| **OpenAPI Specification** | **JSON** | `https://user-management-backend-xxxx.onrender.com/api/v1/openapi.json` |

> *Note: Update the `xxxx` subdomain with your designated service name once deployed on Render and Vercel dashboards.*

---

## 1. Authentication Architecture

The platform enforces a strict separation between frontend tenant sessions and outside programmatic API consumers:

```
[ Tenant Signup ] ---> POST /auth/register (username + password only, no client_id/secret yet)
                             │
                             ▼
[ Tenant Dashboard ] -> POST /auth/login (username + password)
                             │
                             ▼
                     Session JWT (role: client, type: session)
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
   Access Dashboard Data        POST /clients/credentials
(/users, /activity, /insights)    (Generates client_id + client_secret ONCE,
                                   stores bcrypt hash, returns secret only once)
                                            │
                                            ▼
[ Outside API Consumers ] ------------> POST /auth/token
                                  (client_id + client_secret)
                                            │
                                            ▼
                                 API JWT (role: client, type: api)
                                  (Programmatic access only)
```

### Endpoints Overview:
1. **Client Registration (`POST /auth/register`)**:
   - Accepts `username` and `password` only.
   - Stores bcrypt hash in Supabase `clients` table.
   - Does **not** issue API credentials at signup.
2. **Client Login (`POST /auth/login`)**:
   - Verifies `username` + `password`.
   - Issues a signed **Session JWT** (`role: client`, `type: session`).
   - Protects frontend dashboard routes (`/users`, `/activity`, `/insights`, `/clients/credentials`, `/clients/me`).
3. **One-Time External Credentials Generation (`POST /clients/credentials`)**:
   - Requires valid **Session JWT**.
   - Generates unique `client_id` (`cli_...`) and `client_secret` (`sec_...`) **ONCE**.
   - Stores bcrypt hash of secret in Supabase.
   - Returns raw secret only this single time. Subsequent attempts return HTTP 409 Conflict.
4. **External Consumer Programmatic Access**:
   - **Method A (OAuth2 Token Exchange)**: `POST /auth/token` exchanges `client_id` + `client_secret` for an **API JWT** (`type: api`).
   - **Method B (Direct Headers)**: Pass `X-Client-Id` and `X-Client-Secret` (or HTTP Basic Auth) directly on `/users` endpoints for instant programmatic calls without a separate token exchange step.

---

## 2. Super Admin Engine (Platform-Wide Governance)

A completely decoupled Super Admin role with zero tenant scoping:

- **Supabase Table**: `admins` (`id`, `username`, `password_hash`, `role='super_admin'`).
- **Super Admin Login (`POST /admin/auth/login`)**:
  - Authenticates with `username` and `password`.
  - Returns an **Admin JWT** with **no `client_id` and no tenant scoping**.
- **Tenant Isolation Bypass & Global Governance**:
  - `GET /admin/users`: View all registered users across all clients/tenants with search, status, and role filters.
  - `GET /admin/clients`: List all registered clients with user counts, credential status, and platform credentials_count summary.
  - `GET /admin/stats` (`GET /admin/overview`): Global dashboard overview with total registered users, client credentials count, and endpoints usage breakdown.
  - `GET /admin/clients/:id/users`: Drill into any client's user directory (with search and status filters).
  - `POST /admin/clients/:id/users`: Create a user under any specified client.
  - `GET /admin/clients/:id/users/:userId`: Retrieve user from any client.
  - `PUT /admin/clients/:id/users/:userId`: Update user from any client.
  - `DELETE /admin/clients/:id/users/:userId`: Soft-delete/deactivate user from any client.
  - `PATCH /admin/clients/:id/status`: Activate or deactivate any tenant client.
  - `DELETE /admin/clients/:id`: Delete a client and cascade user deactivations.
  - `GET /admin/activity`: Global telemetry logs across all tenants with platform performance metrics.

### Provisioning a Super Admin
Super admins cannot self-register via public API routes. Provision the initial super admin via CLI:
```bash
# Python
python seed_admin.py --username admin --password your_secure_password

# Node.js
node seed_admin.js --username admin --password your_secure_password
```

---

## 3. Firebase Storage (Profile Pictures Only)

Firebase's role is dedicated solely to user profile pictures:
- User avatars are uploaded to Firebase Storage via Admin SDK.
- Public media URLs are saved in MongoDB user documents under `avatar_url`.
- Supports both multipart uploads and base64 encoded strings during user creation/updates.
- FCM notification-on-create/delete use cases are removed; Storage is Firebase's sole job.

---

## 4. Local Development

### Prerequisites
- Python 3.11+ or Node.js 18+
- MongoDB (local or Atlas URI)
- Supabase (PostgreSQL)

### Setup & Run (FastAPI)
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env

# 3. Seed initial Super Admin
python seed_admin.py --username admin --password admin123456

# 4. Start development server
python -m uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

### Setup & Run (Node.js Express)
```bash
# 1. Install dependencies
npm install

# 2. Seed initial Super Admin
node seed_admin.js --username admin --password admin123456

# 3. Start development server
npm run dev
```

### Integration Test Suites
Run the 16-step automated test suite covering registration, login, one-time credentials, API token, tenant isolation, avatar storage, and Super Admin CRUD:
```bash
python test_fastapi.py
```

---

## 5. Render Deployment Guide (/backend)

Deploy the backend to Render using the included Docker configuration or Python environment.

### GitHub Repository Setup
Ensure your latest changes are pushed to GitHub:
```bash
git add .
git commit -m "feat: updated auth model, super admin engine, firebase storage"
git push -u origin main
```

### Render Service Setup
1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Connect your repository: `https://github.com/kathirkamadurai29/User-management-backend`.
4. Configure settings:
   - **Name**: `user-management-backend`
   - **Runtime**: `Docker` (or `Python 3`)
   - **Dockerfile Path**: `Dockerfile`
   - **Docker Context**: `.`
   - **Plan**: Free
5. Set Environment Variables in the Render Dashboard (**never commit credentials to git**):
   - `PORT`: `10000`
   - `CORS_ORIGIN`: `*` (or your production Vercel frontend URL)
   - `JWT_SECRET`: Random 32+ character secure secret
   - `SUPABASE_URL`: `https://<your-project-ref>.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY`: Supabase service role API key
   - `MONGODB_URI`: `mongodb+srv://...`
   - `MONGODB_DB_NAME`: `user_platform`
   - `FIREBASE_PROJECT_ID`: Firebase project ID
   - `FIREBASE_CLIENT_EMAIL`: Service account email
   - `FIREBASE_PRIVATE_KEY`: Service account private key string (replace `\n` with actual linebreaks)
   - `FIREBASE_STORAGE_BUCKET`: Storage bucket name (e.g. `<project-id>.firebasestorage.app`)
   - `GEMINI_API_KEY`: Gemini API key (for `/insights`)
   - `SUPER_ADMIN_USERNAME`: Initial admin username (e.g. `admin`)
   - `SUPER_ADMIN_PASSWORD`: Initial admin password
6. Click **Deploy Web Service**.
7. Once deployment completes, copy your live Render URL and paste it into the **Live Deployment URLs** table in this README.
