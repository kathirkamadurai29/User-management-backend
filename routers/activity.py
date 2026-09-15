from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from middleware.auth import get_current_tenant
from config.mongodb_client import get_db

router = APIRouter(prefix="/activity", tags=["Activity & Usage"])


def _clean_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return doc
    clean = dict(doc)
    if "_id" in clean:
        clean["_id"] = str(clean["_id"])
    return clean


@router.get(
    "",
    summary="Get basic usage stats and recent activity logs for tenant",
)
async def get_activity(tenant: Dict[str, Any] = Depends(get_current_tenant)):
    client_id = tenant["client_id"]
    db = get_db()
    logs_col = db["activity_logs"]

    cursor = logs_col.find({"client_id": client_id}).sort("timestamp", -1).limit(100)
    logs = [_clean_doc(l) for l in cursor]

    # Calculate statistics
    status_2xx = 0
    status_4xx = 0
    status_5xx = 0
    endpoint_counts: Dict[str, int] = {}

    for log in logs:
        s = log.get("status", 200)
        if 200 <= s < 300:
            status_2xx += 1
        elif 400 <= s < 500:
            status_4xx += 1
        elif s >= 500:
            status_5xx += 1

        ep = f"{log.get('method', 'GET')} {log.get('endpoint', '')}".strip()
        endpoint_counts[ep] = endpoint_counts.get(ep, 0) + 1

    total_requests = len(logs)
    success_rate = round((status_2xx / total_requests) * 100, 1) if total_requests > 0 else 100.0

    return {
        "metrics": {
            "total_requests": total_requests,
            "status_2xx": status_2xx,
            "status_4xx": status_4xx,
            "status_5xx": status_5xx,
            "success_rate_percent": success_rate,
            "endpoints_breakdown": endpoint_counts,
        },
        "logs": logs[:50],
    }
