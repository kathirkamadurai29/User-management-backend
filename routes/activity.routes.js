const express = require('express');
const { getDb } = require('../config/mongodb');
const authMiddleware = require('../middleware/auth');

const router = express.Router();

// Scoped strictly to authenticated tenant
router.use(authMiddleware);

/**
 * GET /api/v1/activity
 * Expose basic usage stats and recent activity logs for the authenticated client
 */
router.get('/', async (req, res, next) => {
  try {
    const clientId = req.client.client_id;
    const db = getDb();
    const col = db.collection('activity_logs');

    // Retrieve logs for this client
    const logs = await col
      .find({ client_id: clientId })
      .sort({ timestamp: -1 })
      .limit(100)
      .toArray();

    // Calculate usage statistics
    let status2xx = 0;
    let status4xx = 0;
    let status5xx = 0;
    const endpointCounts = {};

    logs.forEach((log) => {
      const s = log.status || 200;
      if (s >= 200 && s < 300) status2xx++;
      else if (s >= 400 && s < 500) status4xx++;
      else if (s >= 500) status5xx++;

      const key = `${log.method || 'GET'} ${log.endpoint || ''}`.trim();
      endpointCounts[key] = (endpointCounts[key] || 0) + 1;
    });

    const totalRequests = logs.length;
    const successRate = totalRequests > 0 ? Number(((status2xx / totalRequests) * 100).toFixed(1)) : 100;

    return res.status(200).json({
      metrics: {
        total_requests: totalRequests,
        status_2xx: status2xx,
        status_4xx: status4xx,
        status_5xx: status5xx,
        success_rate_percent: successRate,
        endpoints_breakdown: endpointCounts,
      },
      logs: logs.slice(0, 50),
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
