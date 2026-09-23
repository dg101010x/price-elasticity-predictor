-- Supabase's pre-2026-05-30 default: every new table, sequence and function
-- in public granted to anon, authenticated and service_role. Applied before
-- the migration to prove its REVOKEs close what these open.
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
