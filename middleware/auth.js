const jwt = require('jsonwebtoken');

/**
 * JWT Authentication Middleware
 * Enforces hard tenant isolation by extracting client_id from verified token
 */
function authMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({
      error: {
        code: 'UNAUTHORIZED',
        message: 'Missing or malformed Authorization header. Expected Bearer <token>',
      },
    });
  }

  const token = authHeader.split(' ')[1];
  const secret = process.env.JWT_SECRET || 'development_jwt_secret_key_32_bytes_super_secure_random';

  try {
    const decoded = jwt.verify(token, secret);

    if (!decoded || !decoded.client_id) {
      return res.status(401).json({
        error: {
          code: 'INVALID_TOKEN',
          message: 'Token does not contain a valid tenant client_id claim',
        },
      });
    }

    // Attach verified tenant credentials to request object
    req.client = {
      client_id: decoded.client_id,
      name: decoded.name,
      iat: decoded.iat,
      exp: decoded.exp,
    };

    next();
  } catch (err) {
    if (err.name === 'TokenExpiredError') {
      return res.status(401).json({
        error: {
          code: 'TOKEN_EXPIRED',
          message: 'JWT access token has expired. Please re-authenticate via POST /auth/token',
        },
      });
    }

    return res.status(401).json({
      error: {
        code: 'INVALID_TOKEN',
        message: 'JWT token signature is invalid or corrupted',
      },
    });
  }
}

module.exports = authMiddleware;
