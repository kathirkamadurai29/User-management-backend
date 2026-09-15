import os
import json
from datetime import datetime, timezone
from typing import Dict, Any
import httpx
from fastapi import APIRouter, Depends
from middleware.auth import get_current_tenant
from config.mongodb_client import get_db

router = APIRouter(prefix="/insights", tags=["Activity & Usage"])


@router.get(
    "",
    summary="Summarize recent activity logs into an AI text insight via LLM",
)
async def get_insights(tenant: Dict[str, Any] = Depends(get_current_tenant)):
    client_id = tenant["client_id"]
    client_name = tenant.get("name", "Tenant")
    db = get_db()

    # Query recent logs
    cursor = db["activity_logs"].find({"client_id": client_id}).sort("timestamp", -1).limit(50)
    logs = list(cursor)

    active_users_count = db["users"].count_documents({
        "client_id": client_id,
        "is_deleted": False,
    })

    if len(logs) == 0:
        return {
            "insight": f"No recent activity recorded for tenant '{client_name}'. Begin managing users to populate operational logs and generate AI insights.",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sample_count": 0,
            "provider": "system",
        }

    # Aggregate statistics
    success_count = 0
    error_count = 0
    endpoints: Dict[str, int] = {}
    total_duration = 0

    for l in logs:
        s = l.get("status", 200)
        if 200 <= s < 400:
            success_count += 1
        else:
            error_count += 1

        ep = f"{l.get('method', 'GET')} {l.get('endpoint', '')}"
        endpoints[ep] = endpoints.get(ep, 0) + 1
        total_duration += l.get("duration_ms", 0)

    avg_latency = round(total_duration / len(logs))
    success_rate = round((success_count / len(logs)) * 100, 1)

    top_endpoints = ", ".join(
        f"{ep} ({cnt}x)"
        for ep, cnt in sorted(endpoints.items(), key=lambda x: x[1], reverse=True)[:3]
    )

    summary_payload = {
        "tenant_id": client_id,
        "tenant_name": client_name,
        "total_recent_requests": len(logs),
        "success_count": success_count,
        "error_count": error_count,
        "success_rate_percent": success_rate,
        "avg_latency_ms": avg_latency,
        "top_endpoints": top_endpoints,
        "active_users_managed": active_users_count,
    }

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    generated_insight = None
    provider = "analytical-engine"

    if api_key and api_key != "your_gemini_api_key_here":
        try:
            prompt = (
                f"You are an executive cloud telemetry analyst. Analyze the following API operational summary for tenant "
                f"\"{client_name}\" ({client_id}) and generate a concise, 2 to 3 sentence operational insight highlighting "
                f"platform health, usage patterns, and reliability:\n"
                f"{json.dumps(summary_payload, indent=2)}\n"
                f"Respond with only the insight text, without Markdown formatting or bullet points."
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                )
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text")
                        if text:
                            generated_insight = text.strip()
                            provider = "gemini-1.5-flash"
        except Exception as llm_err:
            print(f"[AI Insights] Gemini API call notice: {llm_err}")

    # Fallback analytical engine
    if not generated_insight:
        health_status = (
            "optimal operational reliability"
            if success_rate >= 95
            else (
                "moderate reliability with occasional client-side validation notices"
                if success_rate >= 80
                else "heightened error rates requiring telemetry review"
            )
        )
        generated_insight = (
            f"Tenant {client_name} exhibits {health_status} across {len(logs)} recent requests "
            f"with a {success_rate}% success rate (average latency: {avg_latency}ms). "
            f"Primary traffic is focused on {top_endpoints}, serving {active_users_count} active managed accounts."
        )

    return {
        "insight": generated_insight,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(logs),
        "provider": provider,
    }
