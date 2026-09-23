-- ============================================================================
-- Price Sensitivity Lab: accounts, uploads, elasticity runs and insights.
--
-- Tenant boundary: `accounts`. Who belongs to one: `account_memberships`.
-- Every downstream table carries `account_id` and is readable only by that
-- account's members. Nothing a user can write reaches a published number:
-- users may create a data_sources row (and only its identifying columns);
-- sales_observations, elasticity_runs and insights are written by the
-- server with the service role after it has fitted them, so an account
-- cannot insert an estimate it did not compute.
--
-- Additions beyond the original schema sketch, each for a stated need:
--   data_sources.status_reason  the "reason string the UI can show" on failure
--   data_sources.report         column mapping, rows kept/dropped, categories
--                               excluded and why -- shown on the Data page
--   insights.grounding          which run and field each number in an
--                               insight came from, so the UI can trace it
--   create_account()            onboarding in one transaction (account +
--                               owner membership), idempotent per user
--   storage bucket + policies   uploads under {account_id}/, member read,
--                               owner/manage write
-- ============================================================================

-- ------------------------------------------------------------------ tables --

create table public.accounts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  primary_owner_user_id uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table public.account_memberships (
  account_id uuid not null references public.accounts(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member' check (role in ('owner','manage','member')),
  created_at timestamptz not null default now(),
  primary key (account_id, user_id)
);

create table public.data_sources (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  filename text not null,
  storage_path text not null,
  row_count integer,
  status text not null default 'pending' check (status in ('pending','processing','ready','failed')),
  status_reason text,
  report jsonb not null default '{}'::jsonb,
  uploaded_by uuid not null references auth.users(id),
  uploaded_at timestamptz not null default now()
);

create table public.sales_observations (
  id bigint generated always as identity primary key,
  account_id uuid not null references public.accounts(id) on delete cascade,
  data_source_id uuid not null references public.data_sources(id) on delete cascade,
  product_key text not null,
  product_description text,
  category text,
  week_start date not null,
  price numeric not null,
  units_sold integer not null
);

create table public.elasticity_runs (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  data_source_id uuid not null references public.data_sources(id) on delete cascade,
  category text,
  coefficient numeric not null,
  ci_low numeric not null,
  ci_high numeric not null,
  r_squared numeric not null,
  n_observations integer not null,
  run_at timestamptz not null default now()
);

create table public.insights (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references public.accounts(id) on delete cascade,
  elasticity_run_id uuid not null references public.elasticity_runs(id) on delete cascade,
  body text not null,
  model text not null,
  grounding jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

-- ----------------------------------------------------------------- indexes --
-- Every account_id (the RLS predicate) plus the foreign keys that cascade.

create index on public.account_memberships (user_id);
create index on public.data_sources (account_id);
create index on public.sales_observations (account_id);
create index on public.elasticity_runs (account_id);
create index on public.insights (account_id);

create index on public.sales_observations (data_source_id);
create index on public.elasticity_runs (data_source_id);
create index on public.insights (elasticity_run_id);

-- ------------------------------------------------------- membership checks --
-- security definer so the policies below can consult account_memberships
-- without recursing into that table's own policy. auth.uid() is wrapped in
-- a scalar subquery so it is evaluated once per statement, not per row.
-- search_path is empty and every name is schema-qualified, so a caller
-- can't shadow a table or function these run with elevated rights.

create or replace function public.has_role_on_account(target_account_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.account_memberships
    where account_id = target_account_id
      and user_id = (select auth.uid())
  );
$$;

create or replace function public.has_account_role(target_account_id uuid, allowed_roles text[])
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.account_memberships
    where account_id = target_account_id
      and user_id = (select auth.uid())
      and role = any (allowed_roles)
  );
$$;

-- The account a Storage object belongs to: the first folder of its path.
-- NULL (never an error) for a path that doesn't start with a uuid, so a
-- malformed name fails the policy instead of aborting the statement.
create or replace function public.account_id_from_object_path(object_name text)
returns uuid language sql immutable set search_path = '' as $$
  select case
    when (storage.foldername(object_name))[1]
         ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    then ((storage.foldername(object_name))[1])::uuid
  end;
$$;

-- ------------------------------------------------------------- onboarding --
-- One account per user is a v1 UI decision, not a schema constraint: this
-- returns the caller's existing account instead of creating a second one,
-- and the tables above still allow several if that is ever wanted.

create or replace function public.create_account(account_name text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare
  caller uuid := auth.uid();
  cleaned text := pg_catalog.btrim(coalesce(account_name, ''));
  existing uuid;
  created uuid;
begin
  if caller is null then
    raise exception 'sign in before creating an account' using errcode = '42501';
  end if;
  if pg_catalog.char_length(cleaned) = 0 or pg_catalog.char_length(cleaned) > 120 then
    raise exception 'business name must be 1 to 120 characters' using errcode = '22023';
  end if;

  -- Two onboarding submits racing each other must not make two accounts.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(caller::text, 0));

  select account_id into existing
  from public.account_memberships
  where user_id = caller
  order by created_at
  limit 1;
  if existing is not null then
    return existing;
  end if;

  insert into public.accounts (name, primary_owner_user_id)
  values (cleaned, caller)
  returning id into created;

  insert into public.account_memberships (account_id, user_id, role)
  values (created, caller, 'owner');

  return created;
end;
$$;

-- -------------------------------------------------------- product catalogue --
-- One row per product in an upload -- name, category, typical (median weekly)
-- price -- for the simulator's product picker. Returned as a single JSON
-- value because the Data API caps row-returning responses (1,000 rows by
-- default) and a catalogue can be larger. security invoker: it runs as the
-- caller, so the sales_observations policy decides what it can see.

create or replace function public.product_catalog(target_data_source_id uuid)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select coalesce(pg_catalog.jsonb_agg(pg_catalog.jsonb_build_array(
           p.product_key, p.name, p.category, p.typical_price) order by p.product_key), '[]'::jsonb)
  from (
    select o.product_key,
           coalesce(pg_catalog.max(o.product_description), o.product_key) as name,
           pg_catalog.max(o.category) as category,
           pg_catalog.round(
             (pg_catalog.percentile_cont(0.5) within group (order by o.price))::numeric, 2) as typical_price
    from public.sales_observations o
    where o.data_source_id = target_data_source_id
    group by o.product_key
  ) p;
$$;

-- ---------------------------------------------------------------------- RLS --

alter table public.accounts enable row level security;
alter table public.account_memberships enable row level security;
alter table public.data_sources enable row level security;
alter table public.sales_observations enable row level security;
alter table public.elasticity_runs enable row level security;
alter table public.insights enable row level security;

create policy "members can read their account" on public.accounts
  for select to authenticated using (public.has_role_on_account(id));
create policy "members can read their memberships" on public.account_memberships
  for select to authenticated using (public.has_role_on_account(account_id));
create policy "members can read their data sources" on public.data_sources
  for select to authenticated using (public.has_role_on_account(account_id));
create policy "members can insert data sources" on public.data_sources
  for insert to authenticated
  with check (public.has_role_on_account(account_id) and uploaded_by = (select auth.uid()));
create policy "members can read their sales observations" on public.sales_observations
  for select to authenticated using (public.has_role_on_account(account_id));
create policy "members can read their elasticity runs" on public.elasticity_runs
  for select to authenticated using (public.has_role_on_account(account_id));
create policy "members can read their insights" on public.insights
  for select to authenticated using (public.has_role_on_account(account_id));

-- ------------------------------------------------------------------ grants --
-- Explicit, rather than trusting whatever default privileges the project was
-- created with. Projects created since 2026-05-30 no longer auto-grant new
-- public tables to anon / authenticated / service_role at all (and existing
-- projects switch on 2026-10-30); older ones grant everything. Either way
-- the result is the same: anon gets nothing, authenticated gets exactly what
-- the policies above can ever allow -- and on data_sources only the
-- identifying columns, so a client cannot insert a row claiming status
-- 'ready' -- and the server's service role gets what it writes.

revoke all on public.accounts, public.account_memberships, public.data_sources,
  public.sales_observations, public.elasticity_runs, public.insights
  from anon, authenticated;

grant select on public.accounts, public.account_memberships, public.data_sources,
  public.sales_observations, public.elasticity_runs, public.insights
  to authenticated;
grant insert (account_id, filename, storage_path, uploaded_by) on public.data_sources to authenticated;

grant select, insert, update, delete on public.accounts, public.account_memberships,
  public.data_sources, public.sales_observations, public.elasticity_runs, public.insights
  to service_role;

-- Functions default to EXECUTE for PUBLIC, and these are callable over the
-- Data API as /rpc/<name>: nobody signed out needs any of them.
revoke all on function public.has_role_on_account(uuid) from public, anon;
revoke all on function public.has_account_role(uuid, text[]) from public, anon;
revoke all on function public.account_id_from_object_path(text) from public, anon;
revoke all on function public.create_account(text) from public, anon;
revoke all on function public.product_catalog(uuid) from public, anon;
grant execute on function public.has_role_on_account(uuid) to authenticated, service_role;
grant execute on function public.has_account_role(uuid, text[]) to authenticated, service_role;
grant execute on function public.account_id_from_object_path(text) to authenticated, service_role;
grant execute on function public.create_account(text) to authenticated, service_role;
grant execute on function public.product_catalog(uuid) to authenticated, service_role;

-- ----------------------------------------------------------------- storage --
-- Private bucket; the server uploads with the member's own token, so these
-- policies -- not server code -- decide who may write.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('sales-uploads', 'sales-uploads', false, 26214400, array['text/csv'])
on conflict (id) do nothing;

create policy "members can read their account's uploads" on storage.objects
  for select to authenticated
  using (
    bucket_id = 'sales-uploads'
    and public.has_role_on_account(public.account_id_from_object_path(name))
  );

create policy "owners and managers can upload" on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'sales-uploads'
    and public.has_account_role(public.account_id_from_object_path(name), array['owner','manage'])
  );
