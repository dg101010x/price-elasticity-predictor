-- ============================================================================
-- The parts of a hosted Supabase database the migration depends on, for
-- running it against a plain local Postgres in tests.
--
-- Mirrors what Supabase provisions: the anon / authenticated / service_role
-- roles and the authenticator login PostgREST switches from, an auth schema
-- whose auth.uid() reads the verified JWT's `sub` from the same GUCs
-- PostgREST sets, and a storage schema with RLS on storage.objects and
-- storage.foldername(). It also reproduces Supabase's historical default
-- privileges on request (supabase_legacy_grants.sql), so the migration is
-- tested against both the current no-auto-grant default and the old
-- grant-everything one.
-- ============================================================================

create role anon nologin noinherit;
create role authenticated nologin noinherit;
create role service_role nologin noinherit bypassrls;
create role authenticator login noinherit;
grant anon, authenticated, service_role to authenticator;

-- ------------------------------------------------------------------- auth --
create schema auth;
grant usage on schema auth to anon, authenticated, service_role;

create table auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique not null,
  encrypted_password text not null,
  email_confirmed_at timestamptz,
  created_at timestamptz not null default now()
);

create function auth.uid() returns uuid language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

create function auth.role() returns text language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.role', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
  )::text
$$;

create function auth.jwt() returns jsonb language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')
  )::jsonb
$$;

grant execute on all functions in schema auth to anon, authenticated, service_role;

-- ---------------------------------------------------------------- storage --
create schema storage;
grant usage on schema storage to anon, authenticated, service_role;

create table storage.buckets (
  id text primary key,
  name text not null unique,
  owner uuid,
  public boolean default false,
  file_size_limit bigint,
  allowed_mime_types text[],
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text references storage.buckets(id),
  name text not null,
  owner uuid,
  owner_id text,
  metadata jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  last_accessed_at timestamptz default now(),
  path_tokens text[] generated always as (string_to_array(name, '/')) stored,
  unique (bucket_id, name)
);
alter table storage.objects enable row level security;

create function storage.foldername(name text) returns text[] language plpgsql immutable as $$
declare
  _parts text[];
begin
  select string_to_array(name, '/') into _parts;
  return _parts[1:array_length(_parts, 1) - 1];
end
$$;

grant all on storage.buckets, storage.objects to anon, authenticated, service_role;
grant execute on all functions in schema storage to anon, authenticated, service_role;

-- ----------------------------------------------------- public schema --
-- Current default for new projects (since 2026-05-30): the roles can reach
-- the schema, but new tables are granted to nobody. The migration has to
-- grant what it needs. supabase_legacy_grants.sql layers the old
-- grant-everything default on top, and the RLS suite runs under both.
grant usage on schema public to anon, authenticated, service_role;
