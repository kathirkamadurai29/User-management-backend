const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const {
  getClientByUsername,
  getClientByClientId,
  insertClientAccount,
} = require('../config/supabase');

const router = express.Router();
const JWT_SECRET = process.env.JWT_SECRET || 'development_jwt_secret_key_32_bytes_super_secure_random';

/**
 * POST /auth/register
 * Client signs up with username + password only (no client_id/secret yet)
 */
router.post('/register', async (req, res, next) => {
  try {
    const { username, password, name, email } = req.body;

    if (!username || typeof username !== 'string' || username.trim().length < 3) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Username must be at least 3 characters.',
        },
      });
    }

    if (!password || typeof password !== 'string' || password.length < 6) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Password must be at least 6 characters.',
        },
      });
    }

    const cleanUser = username.trim().toLowerCase();
    const existing = await getClientByUsername(cleanUser);
    if (existing) {
      return res.status(409).json({
        error: {
          code: 'USERNAME_EXISTS',
          message: `A client with username '${cleanUser}' already exists.`,
        },
      });
    }

    const salt = await bcrypt.genSalt(10);
    const passwordHash = await bcrypt.hash(password, salt);

    const client = await insertClientAccount({
      username: cleanUser,
      password_hash: passwordHash,
      name: name ? name.trim() : cleanUser,
      email: email ? email.trim().toLowerCase() : null,
    });

    return res.status(201).json({
      message: 'Client account registered successfully.',
      username: client.username,
      name: client.name || client.username,
      created_at: client.created_at || new Date().toISOString(),
    });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /auth/login
 * Client signs in with username + password yielding Session JWT (role: client)
 */
router.post('/login', async (req, res, next) => {
  try {
    const { username, password } = req.body;

    if (!username || !password) {
      return res.status(400).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'Username and password are required.',
        },
      });
    }

    const cleanUser = username.trim().toLowerCase();
    const client = await getClientByUsername(cleanUser);

    if (!client) {
      return res.status(401).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'Invalid username or password.',
        },
      });
    }

    if (client.is_active === false) {
      return res.status(403).json({
        error: {
          code: 'ACCOUNT_DEACTIVATED',
          message: 'This client account has been suspended.',
        },
      });
    }

    if (!client.password_hash) {
      return res.status(401).json({
        error: {
          code: 'PASSWORD_NOT_SET',
          message: 'Account was created with legacy credentials. Please contact administrator.',
        },
      });
    }

    const isMatch = await bcrypt.compare(password, client.password_hash);
    if (!isMatch) {
      return res.status(401).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'Invalid username or password.',
        },
      });
    }

    const effectiveTenantId = client.client_id || client.username || String(client.id);

    const tokenPayload = {
      sub: String(client.id || client.username),
      username: client.username,
      name: client.name || client.username,
      client_id: effectiveTenantId,
      role: 'client',
      type: 'session',
      iss: 'user-management-platform',
      aud: 'tenant-dashboard',
    };

    const accessToken = jwt.sign(tokenPayload, JWT_SECRET, { expiresIn: '24h' });
    const hasCreds = Boolean(client.client_id && client.client_secret_hash);

    return res.status(200).json({
      access_token: accessToken,
      token_type: 'Bearer',
      expires_in: '24h',
      client: {
        id: String(client.id),
        username: client.username,
        name: client.name || client.username,
        email: client.email,
        client_id: client.client_id,
        has_api_credentials: hasCreds,
      },
    });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /auth/token
 * Outside API consumers exchange client_id + client_secret for API JWT
 */
router.post('/token', async (req, res, next) => {
  try {
    const { client_id, client_secret } = req.body;

    if (!client_id || !client_secret) {
      return res.status(400).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'client_id and client_secret are required.',
        },
      });
    }

    const cleanClientId = client_id.trim();
    const record = await getClientByClientId(cleanClientId);

    if (!record) {
      return res.status(401).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'External API client credentials could not be verified.',
        },
      });
    }

    if (record.is_active === false) {
      return res.status(403).json({
        error: {
          code: 'CLIENT_DEACTIVATED',
          message: 'This client account has been suspended.',
        },
      });
    }

    if (!record.client_secret_hash) {
      return res.status(401).json({
        error: {
          code: 'NO_API_CREDENTIALS',
          message: 'No API secret configured for this client.',
        },
      });
    }

    const isMatch = await bcrypt.compare(client_secret.trim(), record.client_secret_hash);
    if (!isMatch) {
      return res.status(401).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'External API client credentials could not be verified.',
        },
      });
    }

    const tokenPayload = {
      sub: String(record.id || record.client_id),
      client_id: record.client_id,
      username: record.username,
      role: 'client',
      type: 'api',
      iss: 'user-management-platform',
      aud: 'external-api',
    };

    const token = jwt.sign(tokenPayload, JWT_SECRET, { expiresIn: '24h' });

    return res.status(200).json({
      access_token: token,
      token_type: 'Bearer',
      expires_in: '24h',
      client_id: record.client_id,
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
