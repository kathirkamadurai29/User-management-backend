const express = require('express');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { ObjectId } = require('mongodb');
const { adminAuthMiddleware } = require('../middleware/auth');
const {
  getAdminByUsername,
  listAllClients,
  getClientByIdentifier,
  updateClientStatus,
  deleteClientAccount,
} = require('../config/supabase');
const { getDb } = require('../config/mongodb');
const { uploadProfilePicture } = require('../config/firebase');

const router = express.Router();
const JWT_SECRET = process.env.JWT_SECRET || 'development_jwt_secret_key_32_bytes_super_secure_random';

function cleanDoc(doc) {
  if (!doc) return doc;
  const clean = { ...doc };
  if (clean._id) clean._id = clean._id.toString();
  return clean;
}

// -------------------------------------------------------------
// ADMIN AUTHENTICATION
// -------------------------------------------------------------

/**
 * POST /admin/auth/login
 * Authenticate Super Admin with username + password (no client_id, no tenant scoping)
 */
router.post('/auth/login', async (req, res, next) => {
  try {
    const { username, password } = req.body;

    if (!username || !password) {
      return res.status(400).json({
        error: {
          code: 'INVALID_ADMIN_CREDENTIALS',
          message: 'Username and password are required.',
        },
      });
    }

    const cleanUser = username.trim().toLowerCase();
    const admin = await getAdminByUsername(cleanUser);

    if (!admin) {
      return res.status(401).json({
        error: {
          code: 'INVALID_ADMIN_CREDENTIALS',
          message: 'Super Admin authentication failed.',
        },
      });
    }

    const isMatch = await bcrypt.compare(password, admin.password_hash);
    if (!isMatch) {
      return res.status(401).json({
        error: {
          code: 'INVALID_ADMIN_CREDENTIALS',
          message: 'Super Admin authentication failed.',
        },
      });
    }

    const tokenPayload = {
      sub: String(admin.id || admin.username),
      username: admin.username,
      role: 'super_admin',
      iss: 'user-management-platform',
      aud: 'super-admin-portal',
    };

    const accessToken = jwt.sign(tokenPayload, JWT_SECRET, { expiresIn: '24h' });

    return res.status(200).json({
      access_token: accessToken,
      token_type: 'Bearer',
      expires_in: '24h',
      role: 'super_admin',
      admin: {
        id: String(admin.id),
        username: admin.username,
        role: 'super_admin',
      },
    });
  } catch (err) {
    next(err);
  }
});

// All subsequent routes require super_admin JWT
router.use(adminAuthMiddleware);

// -------------------------------------------------------------
// CLIENTS MANAGEMENT (BYPASSES TENANT ISOLATION)
// -------------------------------------------------------------

/**
 * GET /admin/clients
 * List all registered clients with user count and status
 */
router.get('/clients', async (req, res, next) => {
  try {
    const clients = await listAllClients();
    const db = getDb();
    const usersCol = db ? db.collection('users') : null;

    const enriched = await Promise.all(
      clients.map(async (c) => {
        let userCount = 0;
        if (usersCol) {
          const possibleKeys = [c.client_id, c.username, String(c.id)].filter(Boolean);
          userCount = await usersCol.countDocuments({
            client_id: { $in: possibleKeys },
            is_deleted: false,
          });
        }
        return {
          ...c,
          user_count: userCount,
        };
      })
    );

    return res.status(200).json({ clients: enriched, total: enriched.length });
  } catch (err) {
    next(err);
  }
});

/**
 * PATCH /admin/clients/:id/status
 * Activate or deactivate any client
 */
router.patch('/clients/:id/status', async (req, res, next) => {
  try {
    const { id } = req.params;
    const { is_active } = req.body;

    if (typeof is_active !== 'boolean') {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'is_active boolean field is required.',
        },
      });
    }

    const updated = await updateClientStatus(id, is_active);
    if (!updated) {
      return res.status(404).json({
        error: {
          code: 'CLIENT_NOT_FOUND',
          message: `Client '${id}' not found.`,
        },
      });
    }

    return res.status(200).json({
      message: `Client status updated to ${is_active ? 'active' : 'inactive'}.`,
      client: updated,
    });
  } catch (err) {
    next(err);
  }
});

/**
 * DELETE /admin/clients/:id
 * Delete any client and deactivate their users
 */
router.delete('/clients/:id', async (req, res, next) => {
  try {
    const { id } = req.params;
    const client = await getClientByIdentifier(id);
    if (!client) {
      return res.status(404).json({
        error: {
          code: 'CLIENT_NOT_FOUND',
          message: `Client '${id}' not found.`,
        },
      });
    }

    await deleteClientAccount(id);

    // Soft-delete users in MongoDB
    const db = getDb();
    if (db) {
      const possibleKeys = [client.client_id, client.username, String(client.id)].filter(Boolean);
      await db.collection('users').updateMany(
        { client_id: { $in: possibleKeys } },
        {
          $set: {
            is_deleted: true,
            status: 'inactive',
            deleted_at: new Date().toISOString(),
          },
        }
      );
    }

    return res.status(200).json({
      message: `Client '${id}' and all associated tenant records successfully removed.`,
    });
  } catch (err) {
    next(err);
  }
});

// -------------------------------------------------------------
// CLIENT USERS DRILL-DOWN & FULL CRUD
// -------------------------------------------------------------

/**
 * GET /admin/clients/:id/users
 * Drill into any client's users
 */
router.get('/clients/:id/users', async (req, res, next) => {
  try {
    const { id } = req.params;
    const client = await getClientByIdentifier(id);
    if (!client) {
      return res.status(404).json({
        error: {
          code: 'CLIENT_NOT_FOUND',
          message: `Client '${id}' not found.`,
        },
      });
    }

    const db = getDb();
    const usersCol = db.collection('users');
    const possibleKeys = [client.client_id, client.username, String(client.id)].filter(Boolean);

    const query = {
      client_id: { $in: possibleKeys },
      is_deleted: false,
    };

    const { search, status, limit = 50, skip = 0 } = req.query;
    if (status && status !== 'all') {
      query.status = String(status).toLowerCase();
    }
    if (search && String(search).trim()) {
      const term = String(search).trim();
      query.$or = [
        { name: { $regex: term, $options: 'i' } },
        { email: { $regex: term, $options: 'i' } },
      ];
    }

    const users = await usersCol
      .find(query)
      .sort({ created_at: -1 })
      .skip(parseInt(skip, 10) || 0)
      .limit(parseInt(limit, 10) || 50)
      .toArray();

    const total = await usersCol.countDocuments(query);

    return res.status(200).json({
      client: {
        id: String(client.id),
        username: client.username,
        name: client.name,
        client_id: client.client_id,
        is_active: client.is_active !== false,
      },
      users: users.map(cleanDoc),
      total,
      limit: parseInt(limit, 10) || 50,
      skip: parseInt(skip, 10) || 0,
    });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /admin/clients/:id/users
 * Provision user under specified client
 */
router.post('/clients/:id/users', async (req, res, next) => {
  try {
    const { id } = req.params;
    const client = await getClientByIdentifier(id);
    if (!client) {
      return res.status(404).json({
        error: {
          code: 'CLIENT_NOT_FOUND',
          message: `Client '${id}' not found.`,
        },
      });
    }

    const effectiveClientId = client.client_id || client.username || String(client.id);
    const { name, email, role = 'member', status = 'active', avatar_base64, avatar_url, metadata } = req.body;

    if (!name || !email) {
      return res.status(400).json({
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Name and email are required.',
        },
      });
    }

    const db = getDb();
    const usersCol = db.collection('users');
    const possibleKeys = [client.client_id, client.username, String(client.id)].filter(Boolean);

    const existing = await usersCol.findOne({
      client_id: { $in: possibleKeys },
      email: email.toLowerCase(),
      is_deleted: false,
    });

    if (existing) {
      return res.status(409).json({
        error: {
          code: 'USER_ALREADY_EXISTS',
          message: `User with email '${email}' already exists for client '${id}'.`,
        },
      });
    }

    let finalAvatarUrl = avatar_url || null;
    if (avatar_base64) {
      try {
        let rawB64 = avatar_base64.trim();
        let contentType = 'image/jpeg';
        if (rawB64.startsWith('data:') && rawB64.includes(';base64,')) {
          const parts = rawB64.split(';base64,');
          contentType = parts[0].replace('data:', '') || 'image/jpeg';
          rawB64 = parts[1];
        }
        const buffer = Buffer.from(rawB64, 'base64');
        const filename = `${email.replace(/[@.]/g, '_')}.jpg`;
        finalAvatarUrl = await uploadProfilePicture(buffer, filename, contentType, effectiveClientId);
      } catch (uploadErr) {
        console.warn('[Avatar Upload Warning]', uploadErr.message);
      }
    }

    const now = new Date();
    const newUser = {
      client_id: effectiveClientId,
      name: name.trim(),
      email: email.toLowerCase(),
      role,
      status,
      avatar_url: finalAvatarUrl,
      metadata: metadata || {},
      is_deleted: false,
      created_at: now.toISOString(),
      updated_at: now.toISOString(),
    };

    const result = await usersCol.insertOne(newUser);
    newUser._id = result.insertedId || newUser._id;

    return res.status(201).json(cleanDoc(newUser));
  } catch (err) {
    next(err);
  }
});

/**
 * PUT /admin/clients/:id/users/:userId
 * Update user under any client
 */
router.put('/clients/:id/users/:userId', async (req, res, next) => {
  try {
    const { userId } = req.params;
    const db = getDb();
    const usersCol = db.collection('users');

    const idQuery = ObjectId.isValid(userId) ? { _id: new ObjectId(userId) } : { _id: userId };
    const existing = await usersCol.findOne({ ...idQuery, is_deleted: false });

    if (!existing) {
      return res.status(404).json({
        error: {
          code: 'USER_NOT_FOUND',
          message: 'User not found.',
        },
      });
    }

    const { name, role, status, metadata, avatar_base64, avatar_url } = req.body;
    const updates = { updated_at: new Date().toISOString() };

    if (name !== undefined) updates.name = name.trim();
    if (role !== undefined) updates.role = role;
    if (status !== undefined) updates.status = status;
    if (metadata !== undefined) updates.metadata = metadata;

    if (avatar_base64) {
      try {
        let rawB64 = avatar_base64.trim();
        let contentType = 'image/jpeg';
        if (rawB64.startsWith('data:') && rawB64.includes(';base64,')) {
          const parts = rawB64.split(';base64,');
          contentType = parts[0].replace('data:', '') || 'image/jpeg';
          rawB64 = parts[1];
        }
        const buffer = Buffer.from(rawB64, 'base64');
        const filename = `${userId}.jpg`;
        updates.avatar_url = await uploadProfilePicture(buffer, filename, contentType, existing.client_id);
      } catch (uploadErr) {
        console.warn('[Avatar Upload Warning]', uploadErr.message);
      }
    } else if (avatar_url !== undefined) {
      updates.avatar_url = avatar_url;
    }

    await usersCol.updateOne(idQuery, { $set: updates });
    const updated = await usersCol.findOne(idQuery);
    return res.status(200).json(cleanDoc(updated));
  } catch (err) {
    next(err);
  }
});

/**
 * DELETE /admin/clients/:id/users/:userId
 * Soft-delete user under any client
 */
router.delete('/clients/:id/users/:userId', async (req, res, next) => {
  try {
    const { userId } = req.params;
    const db = getDb();
    const usersCol = db.collection('users');

    const idQuery = ObjectId.isValid(userId) ? { _id: new ObjectId(userId) } : { _id: userId };
    const existing = await usersCol.findOne({ ...idQuery, is_deleted: false });

    if (!existing) {
      return res.status(404).json({
        error: {
          code: 'USER_NOT_FOUND',
          message: 'User not found.',
        },
      });
    }

    await usersCol.updateOne(idQuery, {
      $set: {
        is_deleted: true,
        status: 'inactive',
        deleted_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });

    return res.status(200).json({
      message: 'User deactivated successfully by Super Admin',
      id: userId,
    });
  } catch (err) {
    next(err);
  }
});

// -------------------------------------------------------------
// PLATFORM-WIDE TELEMETRY / ACTIVITY LOGS
// -------------------------------------------------------------

/**
 * GET /admin/activity
 * View platform-wide request activity logs across all tenants
 */
router.get('/activity', async (req, res, next) => {
  try {
    const db = getDb();
    const logsCol = db ? db.collection('activity_logs') : null;
    const limit = Math.min(Math.max(parseInt(req.query.limit, 10) || 100, 1), 500);

    let logs = [];
    if (logsCol) {
      logs = await logsCol.find({}).sort({ timestamp: -1 }).limit(limit).toArray();
    }

    let status2xx = 0;
    let status4xx = 0;
    let status5xx = 0;
    const endpointCounts = {};
    const activeTenants = new Set();

    logs.forEach((log) => {
      const s = log.status || 200;
      if (s >= 200 && s < 300) status2xx++;
      else if (s >= 400 && s < 500) status4xx++;
      else if (s >= 500) status5xx++;

      const ep = `${log.method || 'GET'} ${log.endpoint || ''}`.trim();
      endpointCounts[ep] = (endpointCounts[ep] || 0) + 1;

      if (log.client_id) activeTenants.add(log.client_id);
    });

    const totalRequests = logs.length;
    const successRate = totalRequests > 0 ? Math.round((status2xx / totalRequests) * 1000) / 10 : 100.0;

    return res.status(200).json({
      metrics: {
        total_requests: totalRequests,
        status_2xx: status2xx,
        status_4xx: status4xx,
        status_5xx: status5xx,
        success_rate_percent: successRate,
        active_tenants_count: activeTenants.size,
        endpoints_breakdown: endpointCounts,
      },
      logs: logs.map(cleanDoc),
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
