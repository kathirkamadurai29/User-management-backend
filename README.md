# TenantCore — Multi-Tenant User Management & Cloud Platform (Backend Engine)

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_2.0-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11_|_3.14-3776AB?logo=python)](https://python.org)
[![MongoDB](https://img.shields.io/badge/Database-MongoDB_Atlas-47A248?logo=mongodb)](https://www.mongodb.com)
[![Supabase](https://img.shields.io/badge/Auth_DB-Supabase_(PostgreSQL)-3ECF8E?logo=supabase)](https://supabase.com)
[![Firebase](https://img.shields.io/badge/Storage-Firebase_Storage-FFCA28?logo=firebase)](https://firebase.google.com)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render)](https://render.com)
[![Docker](https://img.shields.io/badge/Container-Docker-2496ED?logo=docker)](https://www.docker.com)

Production-ready asynchronous REST backend engineered with FastAPI, featuring hard logical multi-tenant isolation, dual-track authentication (Dashboard Session JWT vs. External Consumer API JWT), Super Admin platform governance, isolated MongoDB user directories, Firebase Cloud Storage for user avatars, and Google Gemini AI telemetry synthesis.

---

## 🌐 Live Production Deployments & URLs

| Service | Host Platform | Production URL |
| :--- | :--- | :--- |
| **Backend REST API** | **Render** | [https://user-management-backend-281v.onrender.com](https://user-management-backend-281v.onrender.com) |
| **Interactive Swagger API Docs** | **Swagger UI** | [https://user-management-backend-281v.onrender.com/api-docs](https://user-management-backend-281v.onrender.com/api-docs) |
| **OpenAPI 3.1 Specification** | **FastAPI / JSON** | [https://user-management-backend-281v.onrender.com/api/v1/openapi.json](https://user-management-backend-281v.onrender.com/api/v1/openapi.json) |
| **Frontend Client Dashboard** | **Vercel** | [https://user-management-frontend-theta.vercel.app](https://user-management-frontend-theta.vercel.app) |
| **Super Admin Platform Portal** | **Vercel** | [https://user-management-frontend-theta.vercel.app/admin](https://user-management-frontend-theta.vercel.app/admin) |
| **Postman Collection** | **Root File** | [postman_collection.json](./postman_collection.json) |

---

## 1. Project Overview & Problem Statement

### Project Overview
TenantCore is a cloud-native SaaS backend built for enterprise multi-tenancy. It allows client organizations to register, manage their private user directories, provision external API credentials on-demand, upload profile avatars to cloud storage, and monitor system telemetry.

### Problem Statement
Traditional multi-tenant implementations frequently risk cross-tenant data leaks due to leaky query abstractions and often conflate human browser logins with machine-to-machine API keys. TenantCore solves these issues through:
1. **Hard Logical Tenant Isolation**: Every query forcibly injects the verified client_id decoded from cryptographically signed JWT tokens.
2. **Dual-Track Security**: Clean separation between human interactive session tokens and programmatic developer API keys.
3. **Optimized Multi-Cloud Storage**: Dual database architecture (PostgreSQL + MongoDB) combined with Google Cloud Storage / Firebase for media files.

---

## 2. System Architecture & Diagram

`mermaid
flowchart TD
    subgraph Clients["Clients & Consumers"]
        Browser["Tenant Admin (Browser)"]
        SuperAdmin["Super Admin (Browser)"]
        ExternalApp["Programmatic API Client"]
    end

    subgraph Hosting["Render Cloud (Container Service)"]
        FastAPI["FastAPI 2.0 REST Engine (Python 3.11 / Uvicorn)"]
        CORS["CORS & Request Validation Middleware"]
        Logging["Activity Logging Middleware (Filtered)"]
        Auth["JWT Auth & Tenant Scoping Resolver"]
        
        FastAPI --> CORS --> Logging --> Auth
    end

    subgraph Storage["Cloud Databases & Storage"]
        Supabase[("Supabase (PostgreSQL)<br/>• Clients & Admins<br/>• Bcrypt Password & Secret Hashes")]
        MongoDB[("MongoDB Atlas<br/>• Tenant Scoped Users<br/>• Activity Logs")]
        Firebase["Firebase Storage (GCS)<br/>• Profile Picture Avatars"]
        Gemini["Google Gemini AI<br/>• Telemetry Insights"]
    end

    Browser -->|Session JWT| FastAPI
    SuperAdmin -->|Admin JWT| FastAPI
    ExternalApp -->|API JWT| FastAPI

    Auth -->|Relational Auth| Supabase
    Auth -->|Scoped User CRUD| MongoDB
    FastAPI -->|Multipart Upload| Firebase
    FastAPI -->|Log Summarization| Gemini
`

---

## 3. Technology Stack

* **Language**: Python 3.11 / 3.14
* **Web Framework**: FastAPI 2.0 with Pydantic v2 validation and Uvicorn ASGI server
* **Databases**: Supabase (PostgreSQL 15) & MongoDB Atlas (Document Store)
* **Cloud Storage**: Firebase Storage (Google Cloud Storage) via irebase-admin
* **AI Engine**: Google Gemini API via google-generativeai with heuristic fallback
* **Security & Auth**: crypt (12 rounds), PyJWT (HS256)
* **Containerization**: Docker, Docker Compose, Linux Alpine/Slim base

---

## 4. Features

* **Multi-Tenant User CRUD**: Complete user management with pagination, debounced search, and status filtering (ll, ctive, pending, inactive).
* **Dual-Track Authentication**: Human registration/login (POST /auth/register, POST /auth/login) separate from programmatic token exchange (POST /auth/token).
* **One-Time Credential Vault**: On-demand generation of client_id + raw client_secret (bcrypt-hashed in Supabase).
* **Firebase Storage Avatars**: Multipart streaming upload directly to Firebase Cloud Storage.
* **Filtered Telemetry Logging**: Automatically records request latency and status codes while suppressing noisy polling endpoints.
* **AI Telemetry Insights**: Automated LLM summarization of tenant operational health.
* **Super Admin Platform Oversight**: Platform-wide tenant directory, tenant suspension toggle, user drilldown, and global metrics.

---

## 5. Prerequisites & Local Setup

### Prerequisites
* Python 3.11+
* Docker & Docker Compose (optional for containerized run)
* MongoDB URI (local or MongoDB Atlas)
* Supabase Project URL & Service Role Key
* Firebase Service Account Key

### Step-by-Step Local Setup

1. **Clone the repository**:
   `ash
   git clone https://github.com/kathirkamadurai29/User-management-backend.git
   cd User-management-backend
   `

2. **Create and activate a virtual environment**:
   `ash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   `

3. **Install dependencies**:
   `ash
   pip install -r requirements.txt
   `

4. **Configure Environment Variables**:
   Copy .env.example to .env and fill in your credentials:
   `ash
   cp .env.example .env
   `

5. **Run the development server**:
   `ash
   uvicorn main:app --host 0.0.0.0 --port 5000 --reload
   `

6. **Access the API**:
   - Health check: http://localhost:5000/health
   - Interactive Swagger docs: http://localhost:5000/api-docs

---

## 6. Docker Setup

To run using Docker Compose:
`ash
docker compose up --build
`
Or build the Docker image standalone:
`ash
docker build -t tenantcore-backend .
docker run -p 5000:5000 --env-file .env tenantcore-backend
`

---

## 7. Environment Variables Reference

| Variable | Description | Example / Default |
| :--- | :--- | :--- |
| PORT | Listening server port | 5000 |
| JWT_SECRET | Cryptographic key for signing JWTs | super_secret_signing_key_32chars |
| JWT_EXPIRES_IN | Token lifespan | 24h |
| SUPABASE_URL | Supabase project URL | https://xxxx.supabase.co |
| SUPABASE_SERVICE_ROLE_KEY | Supabase service role secret | eyJh... |
| MONGODB_URI | MongoDB Atlas or local connection string | mongodb+srv://... |
| MONGODB_DB_NAME | MongoDB database name | user_platform |
| FIREBASE_PROJECT_ID | Firebase project ID | your-firebase-project |
| FIREBASE_CLIENT_EMAIL | Firebase service account email | irebase-adminsdk@... |
| FIREBASE_PRIVATE_KEY | Firebase private RSA key | "-----BEGIN PRIVATE KEY-----\n..." |
| GEMINI_API_KEY | Google Gemini API key | AIzaSy... |

---

## 8. Database Setup

### Supabase (PostgreSQL)
Run the following DDL query in your Supabase SQL Editor:
`sql
CREATE TABLE IF NOT EXISTS clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    organization_name VARCHAR(255),
    password_hash VARCHAR(255) NOT NULL,
    client_id VARCHAR(100) UNIQUE,
    client_secret_hash VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'super_admin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
`

### MongoDB Atlas
Create a database named user_platform with collections:
- users: Indexed on { client_id: 1, is_deleted: 1 }
- ctivity_logs: Indexed on { client_id: 1, timestamp: -1 }

---

## 9. API Documentation & Endpoints

Complete documentation is available interactively at /api-docs. See [docs/API_DOCUMENTATION.md](./docs/API_DOCUMENTATION.md) and [postman_collection.json](./postman_collection.json) for the full catalog.

### Core Endpoints Summary:
- POST /api/v1/auth/register — Self-register new tenant organization
- POST /api/v1/auth/login — Authenticate and receive Session JWT
- POST /api/v1/clients/credentials — Generate client_id + raw client_secret (shown once)
- POST /api/v1/auth/token — Exchange credentials for machine API JWT
- POST /api/v1/users — Create tenant user
- GET  /api/v1/users — List tenant users (with search and status filter)
- GET  /api/v1/users/{id} — Retrieve user (strictly isolated to tenant)
- PUT  /api/v1/users/{id} — Update user
- DELETE /api/v1/users/{id} — Soft delete / deactivate user
- POST /api/v1/users/upload-avatar — Upload avatar to Firebase Storage
- GET  /api/v1/activity — View tenant audit telemetry
- GET  /api/v1/insights — AI operational health summary
- POST /api/v1/admin/auth/login — Super Admin portal login
- GET  /api/v1/admin/clients — Super Admin view of all tenants
- GET  /api/v1/admin/stats — Platform-wide metrics

---

## 10. Deployment Instructions

### Deploy to Render
1. Create a new **Web Service** on Render.
2. Connect your GitHub repository User-management-backend.
3. Set **Runtime** to Docker or Python 3.
4. Configure environment variables matching .env.example.
5. Deploy. Health check endpoint: https://<service-name>.onrender.com/health.

---

## 11. Known Limitations & Future Improvements

### Known Limitations
* **Cold Starts on Free Cloud Tiers**: Free cloud container tiers may exhibit a 20-30 second cold start after inactivity.
* **Single-Region Database**: Supabase and MongoDB Atlas are currently hosted in us-east-1.

### Future Improvements
* Multi-region active-active database replication.
* Distributed Redis caching for token blacklist and rate limiting.
* Webhook event notifications (e.g. user.created, user.deleted) to third-party endpoints.
* OpenTelemetry distributed tracing with Jaeger / Datadog exporter.

---

*Engineered with precision for the Full Stack Cloud Engineer Intern technical evaluation.*
