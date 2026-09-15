const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
const path = require('path');

const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

let supabase = null;
let isConfigured = false;

// Local fallback stores for offline / development resilience
const CLIENTS_FALLBACK_FILE = path.join(__dirname, '..', '.clients_fallback.json');
const ADMINS_FALLBACK_FILE = path.join(__dirname, '..', '.admins_fallback.json');

function readLocal(file) {
  try {
    if (fs.existsSync(file)) {
      return JSON.parse(fs.readFileSync(file, 'utf8'));
    }
  } catch (err) {
    console.error(`[Supabase Fallback] Error reading ${file}:`, err.message);
  }
  return [];
}

function writeLocal(file, data) {
  try {
    fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8');
  } catch (err) {
    console.error(`[Supabase Fallback] Error writing ${file}:`, err.message);
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

// -------------------------------------------------------------
// CLIENTS (TENANTS)
// -------------------------------------------------------------

async function getClientByUsername(username) {
  if (!username) return null;
  const clean = username.trim().toLowerCase();

  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('clients')
      .select('*')
      .ilike('username', clean)
      .maybeSingle();

    if (!error && data) return data;
  }

  const clients = readLocal(CLIENTS_FALLBACK_FILE);
  return clients.find((c) => (c.username || '').toLowerCase() === clean) || null;
}

async function getClientByClientId(clientId) {
  if (!clientId) return null;
  const clean = clientId.trim();

  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('clients')
      .select('*')
      .eq('client_id', clean)
      .maybeSingle();

    if (!error && data) return data;
  }

  const clients = readLocal(CLIENTS_FALLBACK_FILE);
  return clients.find((c) => c.client_id === clean) || null;
}

async function getClientByIdentifier(identifier) {
  if (!identifier) return null;
  const clean = identifier.trim();

  if (isConfigured && supabase) {
    // Try username
    const byUser = await supabase.from('clients').select('*').ilike('username', clean).maybeSingle();
    if (byUser.data) return byUser.data;

    // Try client_id
    const byCli = await supabase.from('clients').select('*').eq('client_id', clean).maybeSingle();
    if (byCli.data) return byCli.data;

    // Try UUID id
    if (clean.length === 36 && clean.includes('-')) {
      const byId = await supabase.from('clients').select('*').eq('id', clean).maybeSingle();
      if (byId.data) return byId.data;
    }
  }

  const clients = readLocal(CLIENTS_FALLBACK_FILE);
  return clients.find(
    (c) =>
      (c.username || '').toLowerCase() === clean.toLowerCase() ||
      c.client_id === clean ||
      String(c.id) === clean
  ) || null;
}

async function insertClientAccount({ username, password_hash, name, email }) {
  const cleanUser = username.trim().toLowerCase();
  const newAccount = {
    id: require('crypto').randomUUID(),
    username: cleanUser,
    password_hash,
    name: name || cleanUser,
    email: email || null,
    client_id: null,
    client_secret_hash: null,
    is_active: true,
    created_at: new Date().toISOString(),
  };

  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('clients')
      .insert([newAccount])
      .select('id, username, name, email, is_active, created_at')
      .single();

    if (error) {
      console.warn('[Supabase] Insert error, fallback to local store:', error.message);
    } else {
      return data;
    }
  }

  const clients = readLocal(CLIENTS_FALLBACK_FILE);
  if (clients.some((c) => (c.username || '').toLowerCase() === cleanUser)) {
    throw new Error(`Client with username '${cleanUser}' already exists.`);
  }
  clients.push(newAccount);
  writeLocal(CLIENTS_FALLBACK_FILE, clients);
  return newAccount;
}

async function generateAndStoreClientCredentials(identifier, clientId, clientSecretHash) {
  if (isConfigured && supabase) {
    const client = await getClientByIdentifier(identifier);
    if (!client) throw new Error(`Client '${identifier}' not found`);

    const { data, error } = await supabase
      .from('clients')
      .update({
        client_id: clientId,
        client_secret_hash: clientSecretHash,
      })
      .eq('id', client.id)
      .select()
      .single();

    if (!error && data) return data;
  }

  const clients = readLocal(CLIENTS_FALLBACK_FILE);
  const idx = clients.findIndex(
    (c) =>
      (c.username || '').toLowerCase() === identifier.toLowerCase() ||
      c.client_id === identifier ||
      String(c.id) === identifier
  );
  if (idx === -1) throw new Error(`Client '${identifier}' not found`);

  clients[idx].client_id = clientId;
  clients[idx].client_secret_hash = clientSecretHash;
  writeLocal(CLIENTS_FALLBACK_FILE, clients);
  return clients[idx];
}

async function listAllClients() {
  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('clients')
      .select('id, username, name, email, client_id, is_active, created_at')
      .order('created_at', { ascending: false });

    if (!error && data) return data;
  }

  const clients = readLocal(CLIENTS_FALLBACK_FILE);
  return clients.map((c) => ({
    id: c.id,
    username: c.username,
    name: c.name,
    email: c.email,
    client_id: c.client_id,
    is_active: c.is_active !== false,
    created_at: c.created_at,
    has_api_credentials: Boolean(c.client_id && c.client_secret_hash),
  }));
}

async function updateClientStatus(identifier, isActive) {
  const client = await getClientByIdentifier(identifier);
  if (!client) return null;

  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('clients')
      .update({ is_active: isActive })
      .eq('id', client.id)
      .select()
      .single();

    if (!error && data) return data;
  }

  const clients = readLocal(CLIENTS_FALLBACK_FILE);
  const idx = clients.findIndex((c) => String(c.id) === String(client.id));
  if (idx !== -1) {
    clients[idx].is_active = isActive;
    writeLocal(CLIENTS_FALLBACK_FILE, clients);
    return clients[idx];
  }
  return null;
}

async function deleteClientAccount(identifier) {
  const client = await getClientByIdentifier(identifier);
  if (!client) return false;

  if (isConfigured && supabase) {
    await supabase.from('clients').delete().eq('id', client.id);
    return true;
  }

  let clients = readLocal(CLIENTS_FALLBACK_FILE);
  clients = clients.filter((c) => String(c.id) !== String(client.id));
  writeLocal(CLIENTS_FALLBACK_FILE, clients);
  return true;
}

// -------------------------------------------------------------
// ADMINS (SUPER ADMINS)
// -------------------------------------------------------------

async function getAdminByUsername(username) {
  if (!username) return null;
  const clean = username.trim().toLowerCase();

  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('admins')
      .select('*')
      .ilike('username', clean)
      .maybeSingle();

    if (!error && data) return data;
  }

  const admins = readLocal(ADMINS_FALLBACK_FILE);
  return admins.find((a) => (a.username || '').toLowerCase() === clean) || null;
}

async function insertAdmin({ username, password_hash, role = 'super_admin' }) {
  const cleanUser = username.trim().toLowerCase();
  const newAdmin = {
    id: require('crypto').randomUUID(),
    username: cleanUser,
    password_hash,
    role,
    created_at: new Date().toISOString(),
  };

  if (isConfigured && supabase) {
    const { data, error } = await supabase
      .from('admins')
      .insert([newAdmin])
      .select('id, username, role, created_at')
      .single();

    if (!error && data) return data;
  }

  const admins = readLocal(ADMINS_FALLBACK_FILE);
  const existingIdx = admins.findIndex((a) => (a.username || '').toLowerCase() === cleanUser);
  if (existingIdx !== -1) {
    admins[existingIdx] = newAdmin;
  } else {
    admins.push(newAdmin);
  }
  writeLocal(ADMINS_FALLBACK_FILE, admins);
  return newAdmin;
}

module.exports = {
  supabase,
  isConfigured,
  getClientByUsername,
  getClientByClientId,
  getClientByIdentifier,
  insertClientAccount,
  generateAndStoreClientCredentials,
  listAllClients,
  updateClientStatus,
  deleteClientAccount,
  getAdminByUsername,
  insertAdmin,
};
