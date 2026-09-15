# TenantCore Backend — Multi-Tenant FastAPI Service & Super Admin Engine

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_2.0-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11_|_3.14-3776AB?logo=python)](https://python.org)
[![MongoDB](https://img.shields.io/badge/Database-MongoDB_Atlas-47A248?logo=mongodb)](https://www.mongodb.com)
[![Supabase](https://img.shields.io/badge/Auth_DB-Supabase_(PostgreSQL)-3ECF8E?logo=supabase)](https://supabase.com)
[![Firebase](https://img.shields.io/badge/Storage-Firebase_Storage-FFCA28?logo=firebase)](https://firebase.google.com)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render)](https://render.com)

Production-ready standalone FastAPI REST backend for multi-tenant user management, dual JWT authentication (Dashboard Session JWT vs. External Consumer API JWT), Supabase credentials, isolated MongoDB user directories, Firebase Storage user avatar processing, and a platform-governing Super Admin engine.

---

## 1. Authentication Architecture

The backend implements strict separation between frontend tenant sessions and outside programmatic API consumers:

- **Client Registration (`POST /auth/register`)**: Accepts `username` and `password`. Bcrypt-hashes password into Supabase `clients` table.
- **Client Login (`POST /auth/login`)**: Returns a signed **Session JWT** (`role: client`, `type: session`) protecting dashboard endpoints (`/users`, `/activity`, `/insights`, `/clients/credentials`).
- **One-Time External Credentials (`POST /clients/credentials`)**: Authenticated clients generate `client_id` (`cli_...`) and `client_secret` (`sec_...`) **ONCE**. Secret is bcrypt-hashed and returned only this single time.
- **External API Consumer Token (`POST /auth/token`)**: Outside systems exchange `client_id` + `client_secret` for an **API JWT** (`type: api`).
- **Super Admin Login (`POST /admin/auth/login`)**: Privileged credentials verified against `admins` table. Issues an **Admin JWT** with **no `client_id` and no tenant scoping**, bypassing all tenant isolation.

---

## 2. Super Admin Capabilities & Seeding

The Super Admin engine provides platform-wide governance:
- `GET /admin/clients`: List all registered clients with user counts and active statuses.
- `GET /admin/clients/:id/users`: Drill into any client's user directory.
- `POST /admin/clients/:id/users`: Provision users for any client (with optional avatar upload).
- `PUT /admin/clients/:id/users/:userId`: Update user details.
- `DELETE /admin/clients/:id/users/:userId`: Deactivate user.
- `PATCH /admin/clients/:id/status`: Activate or deactivate any client.
- `DELETE /admin/clients/:id`: Delete a client and cascade user deactivations.
- `GET /admin/activity`: Global telemetry logs across all tenants.

### Seed Super Admin CLI Script
Super admins cannot register through public routes. Seed the initial admin via CLI:
```bash
python seed_admin.py --username admin --password your_secure_password
```

---

## 3. Firebase Storage Integration
- User profile pictures are uploaded directly to Firebase Storage via Admin SDK (`firebase_client.py`).
- Public media URLs are persisted in the `avatar_url` field of the MongoDB user document.
- Resilient base64 data URI fallback is active when the Firebase storage bucket is offline or unprovisioned.

---

## 4. Local Development

### Prerequisites
- Python 3.11+
- MongoDB (local or Atlas URI)
- Supabase (PostgreSQL)

### Setup & Run
```bash
# 1. Create and activate virtual environment (optional)
python -m venv venv
# On Windows: venv\Scripts\activate
# On macOS/Linux: source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env with your MongoDB, Supabase, and JWT credentials

# 4. Seed initial Super Admin
python seed_admin.py --username admin --password admin123456

# 5. Start development server
python -m uvicorn main:app --host 0.0.0.0 --port 5000 --reload
```

- API Base: `http://localhost:5000/api/v1`
- Interactive Swagger UI: `http://localhost:5000/api-docs`
- Healthcheck: `http://localhost:5000/health`

### Automated Integration Testing
Run the complete 16-step integration test suite:
```bash
python test_fastapi.py
```

---

## 5. GitHub & Render Deployment Guide

### Push to a New GitHub Repository
```bash
git init
git add .
git commit -m "feat: initial backend repository setup"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-backend-repo>.git
git push -u origin main
```

### Deploy to Render
1. Go to [Render Dashboard](https://dashboard.render.com) and click **New +** -> **Web Service**.
2. Connect your backend GitHub repository.
3. Configure settings:
   - **Name**: `user-management-backend`
   - **Runtime**: `Docker`
   - **Dockerfile Path**: `Dockerfile`
   - **Docker Context**: `.`
   - **Plan**: Free (or Starter)
4. Configure Environment Variables in the Render Dashboard (**never committed to git**):
   - `PORT`: `10000`
   - `CORS_ORIGIN`: Your deployed Vercel frontend URL or `*`
   - `JWT_SECRET`: Random 32+ character string
   - `SUPABASE_URL`: `https://<your-project>.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase Service Role Key
   - `MONGODB_URI`: `mongodb+srv://...`
   - `MONGODB_DB_NAME`: `user_platform`
   - `FIREBASE_PROJECT_ID`: Firebase project ID
   - `FIREBASE_CLIENT_EMAIL`: Firebase service account email
   - `FIREBASE_PRIVATE_KEY`: Service account private key string
   - `FIREBASE_STORAGE_BUCKET`: Storage bucket name
   - `GEMINI_API_KEY`: Gemini API key
   - `SUPER_ADMIN_USERNAME`: Initial admin username
   - `SUPER_ADMIN_PASSWORD`: Initial admin password
5. Click **Create Web Service**. Render will build the container and deploy the FastAPI service.
