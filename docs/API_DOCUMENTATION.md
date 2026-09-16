# REST API Reference & Specification
## AI-Enabled Multi-Tenant User Management & Cloud Platform

**Base URL (Production)**: `https://user-management-backend-281v.onrender.com`  
**Interactive Swagger UI**: `https://user-management-backend-281v.onrender.com/api-docs`  
**OpenAPI Specification JSON**: `https://user-management-backend-281v.onrender.com/api/v1/openapi.json`  
**Postman Collection**: [`postman_collection.json`](../postman_collection.json)  

---

## Authentication Schemes

| Scheme | Header Format | Used By | Scopes / Permissions |
| :--- | :--- | :--- | :--- |
| **Session JWT** | `Authorization: Bearer <session_token>` | Frontend Client Portal (`/`) | Managing tenant users, viewing tenant activity, generating API credentials |
| **API JWT** | `Authorization: Bearer <api_token>` | External API Consumers / Systems | Managing tenant users programmatically |
| **Super Admin JWT** | `Authorization: Bearer <admin_token>` | Super Admin Portal (`/admin`) | Platform-wide oversight, cross-tenant user drilldown, tenant lifecycle governance |

---

## 1. System Endpoints

### 1.1 Service Health Check
* **Endpoint**: `GET /health`
* **Auth**: None
* **Response `200 OK`**:
```json
{
  "status": "healthy",
  "timestamp": "2026-09-16T09:48:00.000Z",
  "version": "1.0.0"
}
```

---

## 2. Client Authentication & Credential Provisioning

### 2.1 Tenant Registration
* **Endpoint**: `POST /api/v1/auth/register`
* **Auth**: None
* **Request Body**:
```json
{
  "username": "acme_corp",
  "password": "SecurePassword123!",
  "organization_name": "Acme Corporation"
}
```
* **Response `201 Created`**:
```json
{
  "message": "Tenant registered successfully",
  "client_id": "cli_9e7196a4bb2f4e89",
  "username": "acme_corp"
}
```

### 2.2 Tenant Interactive Login (Dashboard Session)
* **Endpoint**: `POST /api/v1/auth/login`
* **Auth**: None
* **Request Body**:
```json
{
  "username": "acme_corp",
  "password": "SecurePassword123!"
}
```
* **Response `200 OK`**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "role": "client",
  "type": "session"
}
```

### 2.3 Generate API Credentials (One-Time Generation)
* **Endpoint**: `POST /api/v1/clients/credentials`
* **Auth**: `Authorization: Bearer <session_token>`
* **Response `201 Created`**:
```json
{
  "client_id": "cli_9e7196a4bb2f4e89",
  "client_secret": "sec_88f912c4e2b04f32a68c07e0c4",
  "message": "Store this client_secret securely. It will not be shown again."
}
```

### 2.4 Programmatic Token Exchange
* **Endpoint**: `POST /api/v1/auth/token`
* **Auth**: None
* **Request Body**:
```json
{
  "client_id": "cli_9e7196a4bb2f4e89",
  "client_secret": "sec_88f912c4e2b04f32a68c07e0c4"
}
```
* **Response `200 OK`**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in": 86400,
  "role": "client",
  "type": "api"
}
```

---

## 3. Tenant User Management (MongoDB Scoped Directory)

### 3.1 Create User
* **Endpoint**: `POST /api/v1/users`
* **Auth**: `Authorization: Bearer <token>`
* **Request Body**:
```json
{
  "name": "Sarah Connor",
  "email": "sarah.connor@example.com",
  "role": "manager",
  "status": "active",
  "avatar_url": "https://storage.googleapis.com/..."
}
```
* **Response `201 Created`**:
```json
{
  "_id": "6aaa66bb5c5583ee5013bb50",
  "client_id": "cli_9e7196a4bb2f4e89",
  "name": "Sarah Connor",
  "email": "sarah.connor@example.com",
  "role": "manager",
  "status": "active",
  "avatar_url": "https://storage.googleapis.com/...",
  "created_at": "2026-09-16T09:48:05.000Z",
  "is_deleted": false
}
```

### 3.2 List Users (With Search & Status Filtering)
* **Endpoint**: `GET /api/v1/users?search=Sarah&status=active&page=1&limit=10`
* **Auth**: `Authorization: Bearer <token>`
* **Response `200 OK`**:
```json
{
  "users": [
    {
      "_id": "6aaa66bb5c5583ee5013bb50",
      "name": "Sarah Connor",
      "email": "sarah.connor@example.com",
      "role": "manager",
      "status": "active",
      "avatar_url": "https://storage.googleapis.com/..."
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 10
}
```

### 3.3 Retrieve Single User
* **Endpoint**: `GET /api/v1/users/{id}`
* **Auth**: `Authorization: Bearer <token>`
* **Response `200 OK`**: User document matching `{id}` and caller's `{client_id}`.
* **Response `404 Not Found`**: Returned if user does not exist OR belongs to another tenant (strict tenant isolation).

### 3.4 Update User
* **Endpoint**: `PUT /api/v1/users/{id}`
* **Auth**: `Authorization: Bearer <token>`
* **Request Body**:
```json
{
  "name": "Sarah Connor-Reese",
  "role": "admin",
  "status": "active"
}
```
* **Response `200 OK`**: Updated user object.

### 3.5 Delete User (Soft Delete / Deactivation)
* **Endpoint**: `DELETE /api/v1/users/{id}`
* **Auth**: `Authorization: Bearer <token>`
* **Response `200 OK`**:
```json
{
  "message": "User deactivated successfully",
  "user_id": "6aaa66bb5c5583ee5013bb50"
}
```

### 3.6 Upload Avatar (Firebase Cloud Storage)
* **Endpoint**: `POST /api/v1/users/upload-avatar`
* **Auth**: `Authorization: Bearer <token>`
* **Content-Type**: `multipart/form-data`
* **Form Field**: `avatar: <binary image>`
* **Response `200 OK`**:
```json
{
  "avatar_url": "https://storage.googleapis.com/user-management-prod.appspot.com/avatars/avatar_6aaa.png"
}
```

---

## 4. Telemetry & AI Operational Insights

### 4.1 Tenant Request Telemetry & Audit Logs
* **Endpoint**: `GET /api/v1/activity?limit=50`
* **Auth**: `Authorization: Bearer <token>`
* **Response `200 OK`**:
```json
[
  {
    "client_id": "cli_9e7196a4bb2f4e89",
    "endpoint": "/api/v1/users",
    "method": "POST",
    "status_code": 201,
    "latency_ms": 42.1,
    "timestamp": "2026-09-16T09:48:05.000Z"
  }
]
```

### 4.2 AI Operational Telemetry Insights
* **Endpoint**: `GET /api/v1/insights`
* **Auth**: `Authorization: Bearer <token>`
* **Response `200 OK`**:
```json
{
  "insights": "Tenant Acme Corporation exhibits optimal operational health with an average latency of 45ms across 12 API requests. 0% error rate detected in recent window.",
  "metrics": {
    "total_requests": 12,
    "avg_latency_ms": 45.2,
    "error_rate_percent": 0.0
  }
}
```

---

## 5. Super Admin Platform Oversight Engine

### 5.1 Super Admin Login
* **Endpoint**: `POST /api/v1/admin/auth/login`
* **Auth**: None
* **Request Body**:
```json
{
  "username": "admin",
  "password": "adminpassword123"
}
```
* **Response `200 OK`**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "role": "super_admin"
}
```

### 5.2 List All Registered Tenants
* **Endpoint**: `GET /api/v1/admin/clients`
* **Auth**: `Authorization: Bearer <admin_token>`
* **Response `200 OK`**: List of all client organizations, user counts, and credential status.

### 5.3 Platform Analytics & Telemetry
* **Endpoint**: `GET /api/v1/admin/stats`
* **Auth**: `Authorization: Bearer <admin_token>`
* **Response `200 OK`**: Total tenants, total active users, and system load.

---

*All endpoints verified live against production deployment on Render.*
