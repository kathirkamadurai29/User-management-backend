const express = require('express');
const { getDb } = require('../config/mongodb');
const authMiddleware = require('../middleware/auth');

const router = express.Router();

router.use(authMiddleware);

/**
 * GET /api/v1/insights
 * Summarize a client's recent activity_logs into a short text insight using an LLM API call
 */
router.get('/', async (req, res, next) => {
  try {
    const clientId = req.client.client_id;
    const clientName = req.client.name || 'Tenant';
    const db = getDb();

    // Fetch recent activity logs for this tenant
    const logs = await db
      .collection('activity_logs')
      .find({ client_id: clientId })
      .sort({ timestamp: -1 })
      .limit(50)
      .toArray();

    // Also fetch active user count
    const activeUsersCount = await db.collection('users').countDocuments({
      client_id: clientId,
      is_deleted: false,
    });

    if (logs.length === 0) {
      return res.status(200).json({
        insight: `No recent activity recorded for tenant "${clientName}". Begin managing users to populate operational logs and generate AI insights.`,
        generated_at: new Date().toISOString(),
        sample_count: 0,
        provider: 'system',
      });
    }

    // Summarize logs data
    let successCount = 0;
    let errorCount = 0;
    const endpoints = {};
    let totalDuration = 0;

    logs.forEach((l) => {
      const s = l.status || 200;
      if (s >= 200 && s < 400) successCount++;
      else errorCount++;

      const ep = `${l.method} ${l.endpoint}`;
      endpoints[ep] = (endpoints[ep] || 0) + 1;
      totalDuration += l.duration_ms || 0;
    });

    const avgDuration = Math.round(totalDuration / logs.length);
    const topEndpoints = Object.entries(endpoints)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([ep, cnt]) => `${ep} (${cnt}x)`)
      .join(', ');

    const summaryPayload = {
      tenant_id: clientId,
      tenant_name: clientName,
      total_recent_requests: logs.length,
      success_count: successCount,
      error_count: errorCount,
      success_rate_percent: Number(((successCount / logs.length) * 100).toFixed(1)),
      avg_latency_ms: avgDuration,
      top_endpoints: topEndpoints,
      active_users_managed: activeUsersCount,
    };

    const apiKey = process.env.GEMINI_API_KEY;
    let generatedInsight = null;
    let provider = 'analytical-engine';

    if (apiKey && apiKey.trim() && apiKey !== 'your_gemini_api_key_here') {
      try {
        const prompt = `You are an executive cloud telemetry analyst. Analyze the following API operational summary for tenant "${clientName}" (${clientId}) and generate a concise, 2 to 3 sentence operational insight highlighting platform health, usage patterns, and reliability:
${JSON.stringify(summaryPayload, null, 2)}
Respond with only the insight text, without Markdown formatting or bullet points.`;

        const response = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${apiKey}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              contents: [{ parts: [{ text: prompt }] }],
            }),
          }
        );

        if (response.ok) {
          const data = await response.json();
          const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;
          if (text) {
            generatedInsight = text.trim();
            provider = 'gemini-1.5-flash';
          }
        } else {
          console.warn('[AI Insights] Gemini API responded with status:', response.status);
        }
      } catch (llmErr) {
        console.warn('[AI Insights] Failed to reach LLM API:', llmErr.message);
      }
    }

    // High-quality deterministic analytical insight fallback
    if (!generatedInsight) {
      const healthStatus =
        summaryPayload.success_rate_percent >= 95
          ? 'optimal operational reliability'
          : summaryPayload.success_rate_percent >= 80
          ? 'moderate reliability with occasional client-side validation notices'
          : 'heightened error rates requiring telemetry review';

      generatedInsight = `Tenant ${clientName} exhibits ${healthStatus} across ${summaryPayload.total_recent_requests} recent requests with a ${summaryPayload.success_rate_percent}% success rate (average latency: ${summaryPayload.avg_latency_ms}ms). Primary traffic is focused on ${summaryPayload.top_endpoints}, serving ${summaryPayload.active_users_managed} active managed accounts.`;
    }

    return res.status(200).json({
      insight: generatedInsight,
      generated_at: new Date().toISOString(),
      sample_count: logs.length,
      provider,
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
