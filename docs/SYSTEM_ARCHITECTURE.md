# System Architecture & Technical Specifications
## AI-Enabled Multi-Tenant User Management & Cloud Platform

This document details the multi-tenant architecture, data flow diagrams, network boundaries, and security perimeters implemented in the platform.

---

## 1. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Users["End Users & Consumers"]
        TenantUser["Tenant Administrator (Web Browser)"]
        SuperAdmin["Super Administrator (Web Browser)"]
        ExternalClient["External Microservice / App (cURL / SDK)"]
    end

    subgraph CDN["Hosting Platform 1: Vercel (Edge CDN)"]
        ReactApp["React 18 Single Page Application"]
        StaticAssets["Vite 5 Bundled Static Assets & Nginx Config"]
        ReactApp --- StaticAssets
    end

    subgraph CloudEngine["Hosting Platform 2: Render (Container Cloud)"]
        FastAPIEngine["FastAPI 2.0 ASGI Server (Python 3.11)"]
        
        subgraph MiddlewarePipeline["Middleware Pipeline"]
            CORS["CORS Policy Middleware"]
            FilterLog["Activity Telemetry Logger (Filtered)"]
            AuthGuard["JWT Security & Tenant Scope Resolver"]
            CORS --> FilterLog --> AuthGuard
        end
        
        subgraph SubRouters["API Routing Controllers"]
            AuthRouter["/api/v1/auth (Registration, Login, Token Exchange)"]
            ClientsRouter["/api/v1/clients (Profile & API Credential Vault)"]
            UsersRouter["/api/v1/users (Tenant Scoped CRUD & Avatars)"]
            AdminRouter["/api/v1/admin (Platform Oversight Engine)"]
            ActivityRouter["/api/v1/activity (Tenant Telemetry)"]
            InsightsRouter["/api/v1/insights (AI Operational Health)"]
        end

        FastAPIEngine --> MiddlewarePipeline
        MiddlewarePipeline --> SubRouters
    end

    subgraph DataPlane["Data Tier & Cloud Storage"]
        SupabasePostgres[("Supabase (PostgreSQL 15)<br/>• clients (UUID, username, bcrypt hashes)<br/>• admins (Super Admin accounts)<br/>• ACID Transaction Engine")]
        MongoCluster[("MongoDB Atlas (Cloud Cluster)<br/>• users collection (Scoped by client_id)<br/>• activity_logs collection (Audit stream)<br/>• Polymorphic Document Store")]
        FirebaseGCS["Firebase Storage (Google Cloud Storage)<br/>• User Profile Pictures (Avatars)<br/>• Global Google Cloud CDN URL Delivery"]
        GeminiAI["Google Gemini AI Engine<br/>• Operational Telemetry Synthesis<br/>• Automated Health Insights"]
    end

    TenantUser -->|HTTPS| ReactApp
    SuperAdmin -->|HTTPS| ReactApp
    ReactApp -->|REST HTTPS + Session JWT| FastAPIEngine
    ExternalClient -->|REST HTTPS + API JWT| FastAPIEngine

    AuthRouter -->|ACID Identity Verification| SupabasePostgres
    ClientsRouter -->|Bcrypt Credential Storage| SupabasePostgres
    AdminRouter -->|Cross-Tenant Directory Query| SupabasePostgres

    UsersRouter -->|Hard Scoped find/insert/update/delete| MongoCluster
    ActivityRouter -->|Append Telemetry & Audit Query| MongoCluster
    AdminRouter -->|Global Platform Metrics| MongoCluster

    UsersRouter -->|Streaming Multipart Upload| FirebaseGCS
    InsightsRouter -->|Log Synthesis Prompt| GeminiAI
```

---

## 2. Authentication & Data Flow Sequences

### Sequence 1: Interactive Dashboard Registration & Login
1. User enters `username` and `password` on the frontend.
2. Frontend calls `POST /api/v1/auth/register`.
3. Backend validates with Pydantic, salts and hashes the password with `bcrypt`, generates a UUID `client_id`, and inserts a record into Supabase `clients`.
4. User logs in via `POST /api/v1/auth/login`.
5. Backend issues a cryptographically signed Session JWT containing `sub: <client_id>`, `role: "client"`, and `type: "session"`.
6. Frontend stores the token and loads the dashboard.

### Sequence 2: One-Time API Credential Provisioning & Machine Token Exchange
1. Tenant clicks "Generate API Credentials" in the Credentials tab.
2. Frontend calls `POST /api/v1/clients/credentials` with Session JWT.
3. Backend generates high-entropy `client_id` (e.g. `cli_9e7196...`) and `client_secret` (e.g. `sec_88f912...`).
4. Backend hashes the secret with `bcrypt` (12 rounds) and saves it to Supabase `clients.client_secret_hash`.
5. The raw `client_secret` is returned to the frontend **only once** and displayed in a modal.
6. Outside programs invoke `POST /api/v1/auth/token` with `client_id` and `client_secret`.
7. Backend verifies against the bcrypt hash and issues an API JWT with `type: "api"`.

### Sequence 3: Tenant User CRUD & Isolation Enforcement
1. Tenant frontend requests `GET /api/v1/users`.
2. Auth middleware validates the JWT and resolves `request.state.tenant = {"client_id": "cli_9e7196..."}`.
3. Users router executes:
   ```python
   cursor = db.users.find({"client_id": tenant["client_id"], "is_deleted": False})
   ```
4. Only documents owned by the caller are returned.
5. If another tenant attempts `GET /api/v1/users/{other_user_id}`, the query returns `None` and the server responds with `HTTP 404 Not Found`.

---

## 3. Network Architecture & Security Boundaries

| Layer | Host / Provider | Protocol | Security Controls |
| :--- | :--- | :--- | :--- |
| **Client Tier** | Vercel Edge CDN | HTTPS / TLS 1.3 | HSTS, CSP, automated DDoS mitigation |
| **Application Tier** | Render Cloud Container | HTTPS / TLS 1.3 | Docker isolation, CORS validation, Pydantic data schemas |
| **Relational Data** | Supabase (AWS us-east-1) | TLS Encrypted PostgreSQL | Service role key isolation, encrypted at rest |
| **Document Data** | MongoDB Atlas (AWS us-east-1) | TLS Encrypted Wire Protocol | IP whitelist, SCRAM-SHA-256 authentication |
| **Object Storage** | Firebase / Google Cloud Storage | HTTPS / Google Cloud IAM | Role-based storage rules, SSL CDN endpoints |

---

*Verified architecture conforming to production cloud engineering standards.*
