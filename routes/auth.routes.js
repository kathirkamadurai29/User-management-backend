const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { getClientByClientId } = require('../config/supabase');
const { validateAuthToken } = require('../middleware/validate');

const router = express.Router();

/**
 * POST /api/v1/auth/token
 * Exchange client_id + client_secret for a signed JWT with client_id embedded as claim
 */
router.post('/token', validateAuthToken, async (req, res, next) => {
  try {
    const { client_id, client_secret } = req.body;

    // Fetch client record from Supabase
    const clientRecord = await getClientByClientId(client_id);

    if (!clientRecord) {
      return res.status(401).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'Client credentials could not be verified.',
        },
      });
    }

    if (clientRecord.is_active === false) {
      return res.status(403).json({
        error: {
          code: 'CLIENT_DEACTIVATED',
          message: 'This client account has been suspended or deactivated.',
        },
      });
    }

    // Compare raw secret against stored bcrypt hash
    const isMatch = await bcrypt.compare(client_secret, clientRecord.client_secret_hash);
    if (!isMatch) {
      return res.status(401).json({
        error: {
          code: 'INVALID_CREDENTIALS',
          message: 'Client credentials could not be verified.',
        },
      });
    }

    // Embed client_id as claim for hard tenant isolation
    const secret = process.env.JWT_SECRET || 'development_jwt_secret_key_32_bytes_super_secure_random';
    const expiresIn = process.env.JWT_EXPIRES_IN || '24h';

    const tokenPayload = {
      client_id: clientRecord.client_id,
      name: clientRecord.name,
      iss: 'user-management-platform',
      aud: 'tenant-api',
    };

    const token = jwt.sign(tokenPayload, secret, { expiresIn });

    return res.status(200).json({
      access_token: token,
      token_type: 'Bearer',
      expires_in: expiresIn,
      client: {
        client_id: clientRecord.client_id,
        name: clientRecord.name,
        email: clientRecord.email,
      },
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
