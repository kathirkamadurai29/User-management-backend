const { getDb } = require('../config/mongodb');

/**
 * Activity Logger Middleware
 * Logs every API request to MongoDB activity_logs collection
 */
function activityLogger(req, res, next) {
  const startTime = Date.now();

  res.on('finish', async () => {
    try {
      // Ignore static asset or swagger documentation queries to keep logs clean
      if (req.originalUrl.startsWith('/api-docs') || req.originalUrl.startsWith('/favicon.ico')) {
        return;
      }

      const clientId = req.client?.client_id || (req.body && req.body.client_id) || 'anonymous';
      const db = getDb();
      const collection = db.collection('activity_logs');

      const logEntry = {
        client_id: clientId,
        endpoint: req.originalUrl || req.url,
        method: req.method,
        status: res.statusCode,
        duration_ms: Date.now() - startTime,
        ip: req.ip || req.headers['x-forwarded-for'] || '127.0.0.1',
        timestamp: new Date(),
      };

      await collection.insertOne(logEntry);
    } catch (err) {
      console.error('[Activity Logger] Failed to record request log:', err.message);
    }
  });

  next();
}

module.exports = activityLogger;
