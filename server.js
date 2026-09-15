require('dotenv').config();
const express = require('express');
const cors = require('cors');
const swaggerUi = require('swagger-ui-express');

const swaggerSpec = require('./config/swagger');
const { connectMongoDB } = require('./config/mongodb');
const { initializeFirebase } = require('./config/firebase');

const activityLogger = require('./middleware/activityLogger');
const { errorHandler, notFoundHandler } = require('./middleware/errorHandler');

// Route modules
const clientsRoutes = require('./routes/clients.routes');
const authRoutes = require('./routes/auth.routes');
const usersRoutes = require('./routes/users.routes');
const activityRoutes = require('./routes/activity.routes');
const insightsRoutes = require('./routes/insights.routes');

const app = express();
const PORT = process.env.PORT || 5000;

// Connect Database & Initialize SDKs
connectMongoDB();
initializeFirebase();

// CORS Configuration - locked to known origins
const allowedOrigins = process.env.CORS_ORIGIN
  ? process.env.CORS_ORIGIN.split(',').map((origin) => origin.trim())
  : ['http://localhost:5173', 'http://127.0.0.1:5173'];

app.use(
  cors({
    origin: (origin, callback) => {
      // Allow requests with no origin (e.g. mobile apps, curl, server-to-server)
      if (!origin) return callback(null, true);
      if (allowedOrigins.indexOf(origin) !== -1 || process.env.NODE_ENV !== 'production') {
        return callback(null, true);
      }
      return callback(new Error('Blocked by CORS policy: Origin not permitted'), false);
    },
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'Accept'],
    credentials: true,
  })
);

// Body Parser
app.use(express.json({ limit: '1mb' }));

// Global Request Activity Logger for MongoDB
app.use(activityLogger);

// Swagger Documentation UI
app.use('/api-docs', swaggerUi.serve, swaggerUi.setup(swaggerSpec, {
  customCss: '.swagger-ui .topbar { display: none }',
  customSiteTitle: 'User Management Platform API Docs',
}));

// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: '1.0.0',
  });
});

// REST API v1 Routes
app.use('/api/v1/clients', clientsRoutes);
app.use('/api/v1/auth', authRoutes);
app.use('/api/v1/users', usersRoutes);
app.use('/api/v1/activity', activityRoutes);
app.use('/api/v1/insights', insightsRoutes);

// 404 & Centralized Error Handlers
app.use(notFoundHandler);
app.use(errorHandler);

// Start server
if (process.env.NODE_ENV !== 'test') {
  app.listen(PORT, () => {
    console.log(`[Server] Multi-tenant User Management API running on http://localhost:${PORT}`);
    console.log(`[Docs] Swagger UI documentation available at http://localhost:${PORT}/api-docs`);
  });
}

module.exports = app;
