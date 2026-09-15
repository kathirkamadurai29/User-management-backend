#!/usr/bin/env node
require('dotenv').config();
const bcrypt = require('bcryptjs');
const { getAdminByUsername, insertAdmin } = require('./config/supabase');

async function seedSuperAdmin(username, rawPassword) {
  console.log('==================================================');
  console.log('        SUPER ADMIN SEEDING UTILITY (Node)        ');
  console.log('==================================================');

  const cleanUser = (username || '').trim().toLowerCase();
  if (!cleanUser || cleanUser.length < 3) {
    console.error('[ERROR] Admin username must be at least 3 characters.');
    process.exit(1);
  }

  if (!rawPassword || rawPassword.length < 6) {
    console.error('[ERROR] Admin password must be at least 6 characters.');
    process.exit(1);
  }

  console.log(`Checking for existing admin '${cleanUser}'...`);
  const existing = await getAdminByUsername(cleanUser);
  if (existing) {
    console.log(`[NOTE] Admin '${cleanUser}' already exists in database.`);
    console.log(`       Role: ${existing.role || 'super_admin'}`);
    return existing;
  }

  console.log('Hashing password with bcrypt...');
  const salt = await bcrypt.genSalt(10);
  const passwordHash = await bcrypt.hash(rawPassword, salt);

  console.log('Persisting super admin into Supabase admins table...');
  const admin = await insertAdmin({
    username: cleanUser,
    password_hash: passwordHash,
    role: 'super_admin',
  });

  console.log('\n[SUCCESS] Super Admin successfully provisioned!');
  console.log(`  Username : ${admin.username}`);
  console.log(`  Role     : ${admin.role}`);
  console.log(`  ID       : ${admin.id}`);
  console.log('\nYou can now sign in at the /admin portal using these credentials.');
  return admin;
}

const args = process.argv.slice(2);
let u = process.env.SUPER_ADMIN_USERNAME || 'admin';
let p = process.env.SUPER_ADMIN_PASSWORD || 'admin123456';

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--username' || args[i] === '-u') u = args[i + 1];
  if (args[i] === '--password' || args[i] === '-p') p = args[i + 1];
}

seedSuperAdmin(u, p)
  .then(() => process.exit(0))
  .catch((err) => {
    console.error('[FATAL] Failed to seed super admin:', err.message);
    process.exit(1);
  });
