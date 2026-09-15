import time
import jwt
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from config.mongodb_client import get_db

JWT_SECRET = "development_jwt_secret_key_32_bytes_super_secure_random"


class ActivityLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip internal docs or favicon
        path = request.url.path
        if path.startswith("/api-docs") or path.startswith("/openapi.json") or path == "/favicon.ico":
            return await call_next(request)

        start_time = time.perf_counter()

        # Try to extract client_id from Authorization header if present
        client_id = "anonymous"
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1].strip()
            try:
                decoded = jwt.decode(token, options={"verify_signature": False})
                client_id = decoded.get("client_id", "anonymous")
            except Exception:
                pass

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            try:
                db = get_db()
                log_entry = {
                    "client_id": client_id,
                    "endpoint": path,
                    "method": request.method,
                    "status": status_code,
                    "duration_ms": duration_ms,
                    "ip": request.client.host if request.client else "127.0.0.1",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                db["activity_logs"].insert_one(log_entry)
            except Exception as e:
                print(f"[Activity Logger] Error saving request telemetry: {e}")

        return response
