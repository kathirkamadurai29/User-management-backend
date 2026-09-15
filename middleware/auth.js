const jwt = require('jsonwebtoken');

const JWT_SECRET = process.env.JWT_SECRET || 'development_jwt_secret_key_32_bytes_super_secure_random';

/**
 * Tenant Auth Middleware
 * Enforces tenant scoping by validating Session JWT or API JWT
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

  const token = authHeader.split(' ')[1].trim();

  try {
    const decoded = jwt.verify(token, JWT_SECRET);

    if (decoded.role === 'super_admin') {
      req.client = {
        client_id: decoded.client_id || 'admin_global',
        username: decoded.username || 'admin',
        role: 'super_admin',
        is_super_admin: true,
      };
      return next();
    }

    const clientId = decoded.client_id || decoded.username || decoded.sub;
    if (!clientId) {
      return res.status(401).json({
        error: {
          code: 'INVALID_TOKEN',
          message: 'Token does not contain a valid tenant identity claim',
        },
      });
    }

    req.client = {
      client_id: clientId,
      username: decoded.username,
      name: decoded.name || decoded.username || 'Tenant',
      role: decoded.role || 'client',
      type: decoded.type || 'session',
      sub: decoded.sub,
      iat: decoded.iat,
      exp: decoded.exp,
    };

    next();
  } catch (err) {
    if (err.name === 'TokenExpiredError') {
      return res.status(401).json({
        error: {
          code: 'TOKEN_EXPIRED',
          message: 'JWT access token has expired. Please re-authenticate.',
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

/**
 * Super Admin Auth Middleware
 * Validates admin JWT, ensures role='super_admin' and no tenant scoping
 */
function adminAuthMiddleware(req, res, next) {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({
      error: {
        code: 'UNAUTHORIZED',
        message: 'Missing or malformed Authorization header. Expected Bearer <admin-token>',
      },
    });
  }

  const token = authHeader.split(' ')[1].trim();

  try {
    const decoded = jwt.verify(token, JWT_SECRET);

    if (decoded.role !== 'super_admin') {
      return res.status(403).json({
        error: {
          code: 'FORBIDDEN',
          message: 'Access restricted: Super Admin privileges required.',
        },
      });
    }

    req.admin = {
      id: decoded.sub,
      username: decoded.username,
      role: 'super_admin',
      iat: decoded.iat,
      exp: decoded.exp,
    };

    next();
  } catch (err) {
    if (err.name === 'TokenExpiredError') {
      return res.status(401).json({
        error: {
          code: 'TOKEN_EXPIRED',
          message: 'Admin session token has expired. Please sign in again.',
        },
      });
    }

    return res.status(401).json({
      error: {
        code: 'INVALID_TOKEN',
        message: 'Admin token signature is invalid or corrupted',
      },
    });
  }
}

module.exports = authMiddleware;
module.exports.authMiddleware = authMiddleware;
module.exports.adminAuthMiddleware = adminAuthMiddleware;
