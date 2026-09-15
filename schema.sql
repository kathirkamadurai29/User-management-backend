-- ====================================================================
-- Multi-Tenant User Management Platform: Supabase Database Schema
-- ====================================================================
-- Run this SQL in your Supabase SQL Editor to initialize or update the database.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Clients Table (Tenant Identities)
CREATE TABLE IF NOT EXISTS public.clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE,
    password_hash TEXT,
    client_id TEXT UNIQUE,
    client_secret_hash TEXT,
    name TEXT,
    email TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    is_active BOOLEAN DEFAULT true NOT NULL
);

-- Migration safety for existing clients table
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS username TEXT UNIQUE;
ALTER TABLE public.clients ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE public.clients ALTER COLUMN client_id DROP NOT NULL;
ALTER TABLE public.clients ALTER COLUMN client_secret_hash DROP NOT NULL;

-- Indices for rapid tenant lookups
CREATE INDEX IF NOT EXISTS idx_clients_username ON public.clients (username);
CREATE INDEX IF NOT EXISTS idx_clients_client_id ON public.clients (client_id);
CREATE INDEX IF NOT EXISTS idx_clients_is_active ON public.clients (is_active);

COMMENT ON TABLE public.clients IS 'Registered API clients/tenants with username + bcrypt password login and optional external API credentials';

-- 2. Super Admins Table (Platform Administration)
CREATE TABLE IF NOT EXISTS public.admins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'super_admin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_admins_username ON public.admins (username);

COMMENT ON TABLE public.admins IS 'Super administrators with platform-wide tenant bypassing privileges';
