/**
 * Input validation helpers for API write operations
 */

function validateClientRegistration(req, res, next) {
  const { name, email } = req.body || {};

  if (!name || typeof name !== 'string' || !name.trim()) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Field "name" is required and must be a non-empty string.',
      },
    });
  }

  if (email && (typeof email !== 'string' || !isValidEmail(email))) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Field "email" must be a valid email address.',
      },
    });
  }

  req.body.name = name.trim();
  if (email) req.body.email = email.trim().toLowerCase();
  next();
}

function validateAuthToken(req, res, next) {
  const { client_id, client_secret } = req.body || {};

  if (!client_id || typeof client_id !== 'string' || !client_id.trim()) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Field "client_id" is required.',
      },
    });
  }

  if (!client_secret || typeof client_secret !== 'string' || !client_secret.trim()) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Field "client_secret" is required.',
      },
    });
  }

  req.body.client_id = client_id.trim();
  req.body.client_secret = client_secret.trim();
  next();
}

function validateUserCreate(req, res, next) {
  const { name, email, role, status } = req.body || {};

  if (!name || typeof name !== 'string' || !name.trim()) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Field "name" is required and must be a non-empty string.',
      },
    });
  }

  if (!email || typeof email !== 'string' || !isValidEmail(email)) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Field "email" is required and must be a valid email address.',
      },
    });
  }

  const validRoles = ['admin', 'member', 'viewer'];
  if (role && !validRoles.includes(role.toLowerCase())) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: `Field "role" must be one of: ${validRoles.join(', ')}.`,
      },
    });
  }

  const validStatuses = ['active', 'inactive', 'pending'];
  if (status && !validStatuses.includes(status.toLowerCase())) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: `Field "status" must be one of: ${validStatuses.join(', ')}.`,
      },
    });
  }

  req.body.name = name.trim();
  req.body.email = email.trim().toLowerCase();
  req.body.role = (role || 'member').toLowerCase();
  req.body.status = (status || 'active').toLowerCase();
  next();
}

function validateUserUpdate(req, res, next) {
  const { name, role, status, metadata } = req.body || {};

  if (name !== undefined) {
    if (typeof name !== 'string' || !name.trim()) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Field "name" must be a non-empty string if provided.',
        },
      });
    }
    req.body.name = name.trim();
  }

  if (role !== undefined) {
    const validRoles = ['admin', 'member', 'viewer'];
    if (!validRoles.includes(String(role).toLowerCase())) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: `Field "role" must be one of: ${validRoles.join(', ')}.`,
        },
      });
    }
    req.body.role = String(role).toLowerCase();
  }

  if (status !== undefined) {
    const validStatuses = ['active', 'inactive', 'pending'];
    if (!validStatuses.includes(String(status).toLowerCase())) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: `Field "status" must be one of: ${validStatuses.join(', ')}.`,
        },
      });
    }
    req.body.status = String(status).toLowerCase();
  }

  if (metadata !== undefined && (typeof metadata !== 'object' || Array.isArray(metadata))) {
    return res.status(400).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Field "metadata" must be a JSON key-value object.',
      },
    });
  }

  next();
}

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

module.exports = {
  validateClientRegistration,
  validateAuthToken,
  validateUserCreate,
  validateUserUpdate,
};
