const { MongoClient, ObjectId } = require('mongodb');
const fs = require('fs');
const path = require('path');

const uri = process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017';
const dbName = process.env.MONGODB_DB_NAME || 'user_platform';

let client = null;
let db = null;
let isConnected = false;

// Fallback in-memory/file storage if MongoDB is not running locally
const FALLBACK_FILE = path.join(__dirname, '..', '.mongo_fallback.json');

function loadFallbackData() {
  try {
    if (fs.existsSync(FALLBACK_FILE)) {
      return JSON.parse(fs.readFileSync(FALLBACK_FILE, 'utf8'));
    }
  } catch (err) {
    console.error('[MongoDB Fallback] Failed to read storage:', err.message);
  }
  return { users: [], activity_logs: [] };
}

function saveFallbackData(data) {
  try {
    fs.writeFileSync(FALLBACK_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (err) {
    console.error('[MongoDB Fallback] Failed to write storage:', err.message);
  }
}

/**
 * Lightweight mock collection matching MongoDB driver interface
 */
class FallbackCollection {
  constructor(name) {
    this.name = name;
  }

  _getData() {
    const all = loadFallbackData();
    if (!all[this.name]) {
      all[this.name] = [];
    }
    return { all, items: all[this.name] };
  }

  async insertOne(doc) {
    const { all, items } = this._getData();
    const newDoc = {
      _id: doc._id || new ObjectId().toString(),
      ...doc,
      created_at: doc.created_at || new Date(),
    };
    items.push(newDoc);
    saveFallbackData(all);
    return { insertedId: newDoc._id, acknowledged: true };
  }

  async findOne(query) {
    const { items } = this._getData();
    return items.find((item) => matchQuery(item, query)) || null;
  }

  find(query = {}) {
    const { items } = this._getData();
    let results = items.filter((item) => matchQuery(item, query));

    const cursor = {
      _sort: null,
      _limit: null,
      _skip: 0,
      sort(spec) {
        cursor._sort = spec;
        return cursor;
      },
      skip(n) {
        cursor._skip = n;
        return cursor;
      },
      limit(n) {
        cursor._limit = n;
        return cursor;
      },
      async toArray() {
        let list = [...results];
        if (cursor._sort) {
          const [key, dir] = Object.entries(cursor._sort)[0];
          list.sort((a, b) => {
            const va = a[key] instanceof Date ? a[key].getTime() : a[key];
            const vb = b[key] instanceof Date ? b[key].getTime() : b[key];
            if (va < vb) return dir === -1 ? 1 : -1;
            if (va > vb) return dir === -1 ? -1 : 1;
            return 0;
          });
        }
        if (cursor._skip) {
          list = list.slice(cursor._skip);
        }
        if (cursor._limit) {
          list = list.slice(0, cursor._limit);
        }
        return list;
      },
    };
    return cursor;
  }

  async updateOne(filter, updateDoc) {
    const { all, items } = this._getData();
    const index = items.findIndex((item) => matchQuery(item, filter));
    if (index === -1) {
      return { matchedCount: 0, modifiedCount: 0 };
    }

    if (updateDoc.$set) {
      items[index] = {
        ...items[index],
        ...updateDoc.$set,
        updated_at: new Date(),
      };
    }

    saveFallbackData(all);
    return { matchedCount: 1, modifiedCount: 1 };
  }

  async countDocuments(query = {}) {
    const { items } = this._getData();
    return items.filter((item) => matchQuery(item, query)).length;
  }

  async createIndex() {
    return true;
  }
}

function matchQuery(item, query) {
  for (const [key, val] of Object.entries(query)) {
    if (key === '$or' && Array.isArray(val)) {
      const anyMatch = val.some((subQuery) => matchQuery(item, subQuery));
      if (!anyMatch) return false;
      continue;
    }

    if (key === '_id') {
      const targetId = val instanceof ObjectId ? val.toString() : val ? val.toString() : '';
      const itemId = item._id ? item._id.toString() : '';
      if (itemId !== targetId) return false;
      continue;
    }

    if (val && typeof val === 'object' && val.$regex) {
      const reg = new RegExp(val.$regex, val.$options || '');
      if (!reg.test(item[key] || '')) return false;
      continue;
    }

    if (item[key] !== val) {
      return false;
    }
  }
  return true;
}

async function connectMongoDB() {
  try {
    client = new MongoClient(uri, { serverSelectionTimeoutMS: 500, connectTimeoutMS: 500 });
    await client.connect();
    db = client.db(dbName);
    isConnected = true;

    // Create indices
    try {
      await db.collection('users').createIndex({ client_id: 1, is_deleted: 1 });
      await db.collection('users').createIndex({ client_id: 1, email: 1 });
      await db.collection('activity_logs').createIndex({ client_id: 1, timestamp: -1 });
    } catch (idxErr) {
      console.warn('[MongoDB] Index creation warning:', idxErr.message);
    }

    console.log(`[MongoDB] Connected successfully to database: ${dbName}`);
  } catch (err) {
    console.warn(`[MongoDB] Connection to ${uri} failed (${err.message}). Using local persistent fallback store.`);
    isConnected = false;
    db = {
      collection: (name) => new FallbackCollection(name),
    };
  }
}

function getDb() {
  if (!db) {
    // Initial fallback if called before async connect finishes
    db = {
      collection: (name) => new FallbackCollection(name),
    };
  }
  return db;
}

module.exports = {
  connectMongoDB,
  getDb,
  ObjectId,
  get isConnected() {
    return isConnected;
  },
};
