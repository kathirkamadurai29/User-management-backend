import os
import sys
from dotenv import load_dotenv

# Ensure backend directory is in sys.path for root and serverless entrypoints
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Load environment variables
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from config.mongodb_client import connect_mongodb
from middleware.logging_middleware import ActivityLoggingMiddleware
from middleware.error_handler import (
    validation_exception_handler,
    http_exception_handler,
    global_exception_handler,
)

from routers.clients import router as clients_router
from routers.auth import router as auth_router
from routers.users import router as users_router
from routers.activity import router as activity_router
from routers.insights import router as insights_router
from routers.admin import router as admin_router

app = FastAPI(
    title="Multi-Tenant User Management Platform API",
    description="Production-ready FastAPI backend with hard tenant isolation, Supabase credentials, MongoDB users CRUD, activity telemetry, AI insights, and Super Admin engine.",
    version="2.0.0",
    docs_url="/api-docs",
    openapi_url="/api/v1/openapi.json",
)

# Connect to database
connect_mongodb()

# CORS Middleware configured for local and cloud/Vercel deployments
raw_origins = os.getenv("CORS_ORIGIN", "*")
if raw_origins == "*" or not raw_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
    )

# Global Request Activity Logger for MongoDB
app.add_middleware(ActivityLoggingMiddleware)

# Standardized Error Handling
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# Healthcheck
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "framework": "FastAPI",
        "version": "2.0.0",
    }

# Mount REST API v1 routes
app.include_router(clients_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(activity_router, prefix="/api/v1")
app.include_router(insights_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")

# Also mount at root for direct paths /auth/*, /clients/*, and /admin/*
app.include_router(auth_router)
app.include_router(clients_router)
app.include_router(admin_router)

# Mount frontend production build as unified single-link platform
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if not os.environ.get("VERCEL") and os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path.startswith("health"):
            raise HTTPException(status_code=404, detail="Not Found")
        target = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    print(f"[Server] Starting unified platform on http://localhost:{port}")
    print(f"[Frontend] Accessible at http://localhost:{port}/")
    print(f"[API] REST API at http://localhost:{port}/api/v1")
    print(f"[Docs] Swagger UI at http://localhost:{port}/api-docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
