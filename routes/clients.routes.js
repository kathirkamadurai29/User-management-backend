const express = require('express');
const crypto = require('crypto');
const bcrypt = require('bcryptjs');
const authMiddleware = require('../middleware/auth');
const {
  getClientByIdentifier,
  generateAndStoreClientCredentials,
} = require('../config/supabase');
const { getDb } = require('../config/mongodb');

const router = express.Router();

/**
 * POST /clients/credentials (requires session JWT)
 * Generates client_id + client_secret ONCE, stores hash, returns secret only this one time
 */
router.post('/credentials', authMiddleware, async (req, res, next) => {
  try {
    const identifier = req.client.username || req.client.sub || req.client.client_id;
    const client = await getClientByIdentifier(identifier);

    if (!client) {
      return res.status(404).json({
        error: {
          code: 'CLIENT_NOT_FOUND',
          message: 'Authenticated client record not found.',
        },
      });
    }

    if (client.client_id && client.client_secret_hash) {
      return res.status(409).json({
        error: {
          code: 'CREDENTIALS_ALREADY_GENERATED',
          message: 'API credentials have already been generated for this client. The secret cannot be retrieved or regenerated.',
          client_id: client.client_id,
        },
      });
    }

    const clientId = `cli_${crypto.randomBytes(10).toString('hex')}`;
    const rawSecret = `sec_${crypto.randomBytes(24).toString('hex')}`;

    const salt = await bcrypt.genSalt(10);
    const secretHash = await bcrypt.hash(rawSecret, salt);

    await generateAndStoreClientCredentials(identifier, clientId, secretHash);

    // Migrate any user records in MongoDB scoped by username to new client_id
    try {
      const db = getDb();
      if (db) {
        const oldTenantId = client.username;
        if (oldTenantId && oldTenantId !== clientId) {
          await db.collection('users').updateMany({ client_id: oldTenantId }, { $set: { client_id: clientId } });
          await db.collection('activity_logs').updateMany({ client_id: oldTenantId }, { $set: { client_id: clientId } });
        }
      }
    } catch (dbErr) {
      console.warn('[MongoDB Migration Notice]', dbErr.message);
    }

    return res.status(201).json({
      client_id: clientId,
      client_secret: rawSecret,
      message: 'External API credentials generated successfully. Save this secret now; it will NEVER be displayed again.',
      created_at: new Date().toISOString(),
    });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /clients/me
 * Profile of current authenticated tenant
 */
router.get('/me', authMiddleware, async (req, res, next) => {
  try {
    const identifier = req.client.username || req.client.sub || req.client.client_id;
    const client = await getClientByIdentifier(identifier);

    if (!client) {
      return res.status(404).json({
        error: {
          code: 'CLIENT_NOT_FOUND',
          message: 'Client profile not found.',
        },
      });
    }

    const hasCreds = Boolean(client.client_id && client.client_secret_hash);

    return res.status(200).json({
      id: String(client.id),
      username: client.username || req.client.username,
      name: client.name || client.username,
      email: client.email,
      client_id: client.client_id,
      has_api_credentials: hasCreds,
      is_active: client.is_active !== false,
      created_at: client.created_at,
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
