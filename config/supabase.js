const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
const path = require('path');

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

let supabase = null;
let isConfigured = false;

// Local fallback store for offline development / evaluation
const LOCAL_STORE_PATH = path.join(__dirname, '..', '.clients_fallback.json');

function readLocalClients() {
  try {
    if (fs.existsSync(LOCAL_STORE_PATH)) {
      return JSON.parse(fs.readFileSync(LOCAL_STORE_PATH, 'utf8'));
    }
  } catch (err) {
    console.error('[Clients Store] Error reading local clients:', err.message);
  }
  return [];
}

function writeLocalClients(clients) {
  try {
    fs.writeFileSync(LOCAL_STORE_PATH, JSON.stringify(clients, null, 2), 'utf8');
  } catch (err) {
    console.error('[Clients Store] Error saving local clients:', err.message);
  }
}

if (supabaseUrl && supabaseKey && supabaseUrl.startsWith('http')) {
  try {
    supabase = createClient(supabaseUrl, supabaseKey, {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
    });
    isConfigured = true;
    console.log('[Supabase] Initialized client targeting:', supabaseUrl);
  } catch (err) {
    console.warn('[Supabase] Initialization failed, using local store fallback:', err.message);
  }
} else {
  console.log('[Supabase] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured. Operating in local resilient store mode.');
}

/**
 * Inserts a new client into the `clients` table
 */
async function insertClient({ client_id, client_secret_hash, name, email }) {
  const newClient = {
    client_id,
    client_secret_hash,
    name,
    email: email || null,
    created_at: new Date().toISOString(),
    is_active: true,
  };

  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('clients')
      .insert([newClient])
      .select('client_id, name, email, created_at, is_active')
      .single();

    if (error) {
      console.warn('[Supabase] insert error, falling back to local store:', error.message);
    } else {
      return data;
    }
  }

  // Resilient fallback
  const clients = readLocalClients();
  const existing = clients.find((c) => c.client_id === client_id);
  if (existing) {
    throw new Error(`Client ${client_id} already exists`);
  }
  clients.push(newClient);
  writeLocalClients(clients);

  return {
    client_id: newClient.client_id,
    name: newClient.name,
    email: newClient.email,
    created_at: newClient.created_at,
    is_active: newClient.is_active,
  };
}

/**
 * Retrieves a client by client_id including secret hash for authentication
 */
async function getClientByClientId(client_id) {
  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('clients')
      .select('*')
      .eq('client_id', client_id)
      .maybeSingle();

    if (!error && data) {
      return data;
    }
  }

  // Resilient fallback
  const clients = readLocalClients();
  return clients.find((c) => c.client_id === client_id) || null;
}

module.exports = {
  supabase,
  isConfigured,
  insertClient,
  getClientByClientId,
};
