#!/usr/bin/env python
"""
Super Admin Seeding Script
==========================
Usage:
    python seed_admin.py [--username USERNAME] [--password PASSWORD]

Or configure via environment variables:
    SUPER_ADMIN_USERNAME=admin
    SUPER_ADMIN_PASSWORD=supersecurepassword

Creates a platform-wide Super Admin record in Supabase with bcrypt hashing.
"""

import os
import sys
import argparse
import asyncio
from dotenv import load_dotenv

# Ensure backend directory is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

load_dotenv(os.path.join(CURRENT_DIR, ".env"))
load_dotenv()

import bcrypt
from config.supabase_client import get_admin_by_username, insert_admin


async def seed_super_admin(username: str, raw_password: str):
    print("==================================================")
    print("        SUPER ADMIN SEEDING UTILITY               ")
    print("==================================================")

    clean_user = username.strip().lower()
    if not clean_user or len(clean_user) < 3:
        print("[ERROR] Admin username must be at least 3 characters.")
        sys.exit(1)

    if not raw_password or len(raw_password) < 6:
        print("[ERROR] Admin password must be at least 6 characters.")
        sys.exit(1)

    print(f"Checking for existing admin '{clean_user}'...")
    existing = await get_admin_by_username(clean_user)
    if existing:
        print(f"[NOTE] Admin '{clean_user}' already exists in database.")
        print(f"       Role: {existing.get('role', 'super_admin')}")
        print("       To update credentials, modify the record in Supabase SQL editor.")
        return existing

    print("Hashing password with bcrypt...")
    salt = bcrypt.gensalt(rounds=10)
    password_hash = bcrypt.hashpw(raw_password.encode("utf-8"), salt).decode("utf-8")

    print("Persisting super admin into Supabase admins table...")
    admin = await insert_admin(
        username=clean_user,
        password_hash=password_hash,
        role="super_admin",
    )

    print("\n[SUCCESS] Super Admin successfully provisioned!")
    print(f"  Username : {admin.get('username')}")
    print(f"  Role     : {admin.get('role')}")
    print(f"  ID       : {admin.get('id')}")
    print("\nYou can now sign in at the /admin portal using these credentials.")
    return admin


def main():
    parser = argparse.ArgumentParser(description="Seed platform super admin")
    parser.add_argument("--username", "-u", default=os.getenv("SUPER_ADMIN_USERNAME", "admin"), help="Super admin username")
    parser.add_argument("--password", "-p", default=os.getenv("SUPER_ADMIN_PASSWORD", "admin123456"), help="Super admin password")

    args = parser.parse_args()
    asyncio.run(seed_super_admin(args.username, args.password))


if __name__ == "__main__":
    main()
