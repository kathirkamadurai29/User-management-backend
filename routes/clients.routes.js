const express = require('express');
const crypto = require('crypto');
const bcrypt = require('bcryptjs');
const { insertClient } = require('../config/supabase');
const { validateClientRegistration } = require('../middleware/validate');

const router = express.Router();

/**
 * POST /api/v1/clients
 * Register a new tenant client, generate client_id + client_secret (bcrypt-hash secret), store in Supabase
 */
router.post('/', validateClientRegistration, async (req, res, next) => {
  try {
    const { name, email } = req.body;

    // Generate secure client_id and client_secret
    const clientId = `cli_${crypto.randomBytes(10).toString('hex')}`;
    const rawSecret = `sec_${crypto.randomBytes(24).toString('hex')}`;

    // Hash client secret using bcrypt
    const saltRounds = 10;
    const clientSecretHash = await bcrypt.hash(rawSecret, saltRounds);

    // Persist into Supabase clients table
    const storedClient = await insertClient({
      client_id: clientId,
      client_secret_hash: clientSecretHash,
      name,
      email: email || null,
    });

    // Return credentials (raw secret is displayed only once)
    return res.status(201).json({
      client_id: storedClient.client_id,
      client_secret: rawSecret,
      name: storedClient.name,
      email: storedClient.email,
      created_at: storedClient.created_at,
      message: 'Client registered successfully. Please securely save the client_secret; it will not be shown again.',
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
