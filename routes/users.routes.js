const express = require('express');
const { getDb, ObjectId } = require('../config/mongodb');
const authMiddleware = require('../middleware/auth');
const { uploadProfilePicture } = require('../config/firebase');

const router = express.Router();

// Apply strict JWT tenant isolation to all /users endpoints
router.use(authMiddleware);

function cleanDoc(doc) {
  if (!doc) return doc;
  const clean = { ...doc };
  if (clean._id) clean._id = clean._id.toString();
  return clean;
}

function buildIdFilter(id, clientId, username) {
  let idClause;
  try {
    if (ObjectId.isValid(id) && String(new ObjectId(id)) === id) {
      idClause = new ObjectId(id);
    } else {
      idClause = id;
    }
  } catch {
    idClause = id;
  }

  const tenantKeys = [clientId, username].filter(Boolean);

  return {
    _id: idClause,
    client_id: { $in: tenantKeys },
  };
}

async function processAvatarBase64(avatarBase64, clientId, identifier) {
  if (!avatarBase64 || typeof avatarBase64 !== 'string') return null;

  try {
    let rawB64 = avatarBase64.trim();
    let contentType = 'image/jpeg';
    if (rawB64.startsWith('data:') && rawB64.includes(';base64,')) {
      const parts = rawB64.split(';base64,');
      contentType = parts[0].replace('data:', '') || 'image/jpeg';
      rawB64 = parts[1];
    }

    const buffer = Buffer.from(rawB64, 'base64');
    const ext = contentType.includes('/') ? contentType.split('/')[1] : 'jpg';
    const filename = `${identifier}.${ext}`;

    return await uploadProfilePicture(buffer, filename, contentType, clientId);
  } catch (err) {
    console.warn('[Avatar Processing Warning]', err.message);
    return avatarBase64.startsWith('http') ? avatarBase64 : null;
  }
}

/**
 * POST /api/v1/users
 * Create a new user scoped to the authenticated tenant with profile picture upload
 */
router.post('/', async (req, res, next) => {
  try {
    const { name, email, role, status, metadata, avatar_base64, avatar_url } = req.body;
    const clientId = req.client.client_id;
    const username = req.client.username;

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
    const tenantKeys = [clientId, username].filter(Boolean);

    // Prevent duplicate active email for this specific tenant
    const existing = await usersCol.findOne({
      client_id: { $in: tenantKeys },
      email: email.toLowerCase(),
      is_deleted: false,
    });

    if (existing) {
      return res.status(409).json({
        error: {
          code: 'USER_ALREADY_EXISTS',
          message: `A user with email "${email}" already exists for this tenant.`,
        },
      });
    }

    let finalAvatarUrl = avatar_url || null;
    if (avatar_base64) {
      const uploaded = await processAvatarBase64(avatar_base64, clientId, email.replace(/[@.]/g, '_'));
      if (uploaded) finalAvatarUrl = uploaded;
    }

    const now = new Date().toISOString();
    const newUser = {
      client_id: clientId,
      name: name.trim(),
      email: email.toLowerCase(),
      role: role || 'member',
      status: status || 'active',
      avatar_url: finalAvatarUrl,
      metadata: metadata || {},
      is_deleted: false,
      created_at: now,
      updated_at: now,
    };

    const result = await usersCol.insertOne(newUser);
    newUser._id = result.insertedId || newUser._id;

    return res.status(201).json(cleanDoc(newUser));
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/v1/users
 * List users scoped strictly to the authenticated tenant with search & status filters
 */
router.get('/', async (req, res, next) => {
  try {
    const clientId = req.client.client_id;
    const username = req.client.username;
    const { search, status, limit, skip } = req.query;

    const db = getDb();
    const usersCol = db.collection('users');
    const tenantKeys = [clientId, username].filter(Boolean);

    // Hard tenant isolation filter
    const query = {
      client_id: { $in: tenantKeys },
      is_deleted: false,
    };

    if (status && status !== 'all') {
      query.status = String(status).toLowerCase();
    }

    if (search && String(search).trim()) {
      const sanitized = String(search).trim();
      query.$or = [
        { name: { $regex: sanitized, $options: 'i' } },
        { email: { $regex: sanitized, $options: 'i' } },
      ];
    }

    const parsedLimit = Math.min(Math.max(parseInt(limit, 10) || 50, 1), 200);
    const parsedSkip = Math.max(parseInt(skip, 10) || 0, 0);

    const users = await usersCol
      .find(query)
      .sort({ created_at: -1 })
      .skip(parsedSkip)
      .limit(parsedLimit)
      .toArray();

    const total = await usersCol.countDocuments(query);

    return res.status(200).json({
      users: users.map(cleanDoc),
      total,
      limit: parsedLimit,
      skip: parsedSkip,
    });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /api/v1/users/:id
 * Retrieve single user by ID ensuring strict tenant isolation
 */
router.get('/:id', async (req, res, next) => {
  try {
    const { id } = req.params;
    const clientId = req.client.client_id;
    const username = req.client.username;
    const db = getDb();
    const usersCol = db.collection('users');

    const filter = {
      ...buildIdFilter(id, clientId, username),
      is_deleted: false,
    };

    const user = await usersCol.findOne(filter);

    if (!user) {
      return res.status(404).json({
        error: {
          code: 'USER_NOT_FOUND',
          message: 'User does not exist or access was denied for this tenant.',
        },
      });
    }

    return res.status(200).json(cleanDoc(user));
  } catch (err) {
    next(err);
  }
});

/**
 * PUT /api/v1/users/:id
 * Update user fields scoped to authenticated tenant
 */
router.put('/:id', async (req, res, next) => {
  try {
    const { id } = req.params;
    const clientId = req.client.client_id;
    const username = req.client.username;
    const { name, role, status, metadata, avatar_base64, avatar_url } = req.body;

    const db = getDb();
    const usersCol = db.collection('users');

    const filter = {
      ...buildIdFilter(id, clientId, username),
      is_deleted: false,
    };

    const existing = await usersCol.findOne(filter);
    if (!existing) {
      return res.status(404).json({
        error: {
          code: 'USER_NOT_FOUND',
          message: 'User does not exist or access was denied for this tenant.',
        },
      });
    }

    const updates = {};
    if (name !== undefined) updates.name = name.trim();
    if (role !== undefined) updates.role = role;
    if (status !== undefined) updates.status = status;
    if (metadata !== undefined) updates.metadata = metadata;

    if (avatar_base64) {
      const uploaded = await processAvatarBase64(avatar_base64, clientId, id);
      if (uploaded) updates.avatar_url = uploaded;
    } else if (avatar_url !== undefined) {
      updates.avatar_url = avatar_url;
    }

    updates.updated_at = new Date().toISOString();

    await usersCol.updateOne(filter, { $set: updates });
    const updatedUser = await usersCol.findOne(filter);
    return res.status(200).json(cleanDoc(updatedUser));
  } catch (err) {
    next(err);
  }
});

/**
 * DELETE /api/v1/users/:id
 * Soft delete / deactivate user scoped strictly to authenticated tenant
 */
router.delete('/:id', async (req, res, next) => {
  try {
    const { id } = req.params;
    const clientId = req.client.client_id;
    const username = req.client.username;
    const db = getDb();
    const usersCol = db.collection('users');

    const filter = {
      ...buildIdFilter(id, clientId, username),
      is_deleted: false,
    };

    const existing = await usersCol.findOne(filter);
    if (!existing) {
      return res.status(404).json({
        error: {
          code: 'USER_NOT_FOUND',
          message: 'User does not exist or access was denied for this tenant.',
        },
      });
    }

    const now = new Date().toISOString();
    await usersCol.updateOne(filter, {
      $set: {
        is_deleted: true,
        status: 'inactive',
        deleted_at: now,
        updated_at: now,
      },
    });

    return res.status(200).json({
      message: 'User deactivated successfully',
      id: id,
      deleted_at: now,
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
