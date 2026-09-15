const express = require('express');
const { getDb, ObjectId } = require('../config/mongodb');
const authMiddleware = require('../middleware/auth');
const { validateUserCreate, validateUserUpdate } = require('../middleware/validate');
const { triggerUserCreatedEvent, triggerUserDeletedEvent } = require('../config/firebase');

const router = express.Router();

// Apply strict JWT tenant isolation to all /users endpoints
router.use(authMiddleware);

/**
 * Helper to build an ID query that works with either ObjectId or string IDs
 */
function buildIdFilter(id, clientId) {
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

  // Hard tenant isolation: ALWAYS enforce client_id
  return {
    _id: idClause,
    client_id: clientId,
  };
}

/**
 * POST /api/v1/users
 * Create a new user scoped to the authenticated tenant
 */
router.post('/', validateUserCreate, async (req, res, next) => {
  try {
    const { name, email, role, status, metadata } = req.body;
    const clientId = req.client.client_id;
    const db = getDb();
    const usersCol = db.collection('users');

    // Prevent duplicate active email for this specific tenant
    const existing = await usersCol.findOne({
      client_id: clientId,
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

    const newUser = {
      client_id: clientId,
      name,
      email: email.toLowerCase(),
      role: role || 'member',
      status: status || 'active',
      metadata: metadata || {},
      is_deleted: false,
      created_at: new Date(),
      updated_at: new Date(),
    };

    const result = await usersCol.insertOne(newUser);
    const createdUser = {
      _id: result.insertedId || newUser._id,
      ...newUser,
    };

    // Firebase Admin notification / event trigger
    triggerUserCreatedEvent(createdUser).catch((err) => {
      console.warn('[Firebase] Event dispatch notice:', err.message);
    });

    return res.status(201).json(createdUser);
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
    const { search, status, limit, skip } = req.query;

    const db = getDb();
    const usersCol = db.collection('users');

    // Hard tenant isolation filter
    const query = {
      client_id: clientId,
      is_deleted: false,
    };

    // Filter by status if provided
    if (status && status !== 'all') {
      query.status = String(status).toLowerCase();
    }

    // Filter by search keyword on name or email
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
      users,
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
    const db = getDb();
    const usersCol = db.collection('users');

    const filter = {
      ...buildIdFilter(id, clientId),
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

    return res.status(200).json(user);
  } catch (err) {
    next(err);
  }
});

/**
 * PUT /api/v1/users/:id
 * Update user fields scoped to authenticated tenant
 */
router.put('/:id', validateUserUpdate, async (req, res, next) => {
  try {
    const { id } = req.params;
    const clientId = req.client.client_id;
    const { name, role, status, metadata } = req.body;

    const db = getDb();
    const usersCol = db.collection('users');

    const filter = {
      ...buildIdFilter(id, clientId),
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
    if (name !== undefined) updates.name = name;
    if (role !== undefined) updates.role = role;
    if (status !== undefined) updates.status = status;
    if (metadata !== undefined) updates.metadata = metadata;
    updates.updated_at = new Date();

    await usersCol.updateOne(filter, { $set: updates });

    const updatedUser = await usersCol.findOne(filter);
    return res.status(200).json(updatedUser);
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
    const db = getDb();
    const usersCol = db.collection('users');

    const filter = {
      ...buildIdFilter(id, clientId),
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

    // Perform soft delete
    await usersCol.updateOne(filter, {
      $set: {
        is_deleted: true,
        status: 'inactive',
        deleted_at: new Date(),
        updated_at: new Date(),
      },
    });

    // Firebase Admin notification / event trigger
    triggerUserDeletedEvent(existing).catch((err) => {
      console.warn('[Firebase] Deletion event dispatch notice:', err.message);
    });

    return res.status(200).json({
      message: 'User deactivated successfully',
      id: id,
      deleted_at: new Date().toISOString(),
    });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
