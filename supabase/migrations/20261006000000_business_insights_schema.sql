-- Business insights platform schema. Tenant boundary = businesses; access via business_members.

create table public.businesses (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  name text not null check (char_length(name) between 1 and 120),
  city text,
  region text,
  country text not null,
  industry text not null,
  description text not null check (array_length(regexp_split_to_array(btrim(description), '\s+'), 1) <= 25),
  competition_scope text not null check (competition_scope in ('local','regional','national','online')),
  key_components jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.business_members (
  business_id uuid not null references public.businesses(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'owner' check (role in ('owner','member')),
  created_at timestamptz not null default now(),
  primary key (business_id, user_id)
);
create index on public.business_members (user_id);

create or replace function public.is_business_member(b uuid)
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.business_members
    where business_id = b and user_id = auth.uid()
  );
$$;

create or replace function public.add_owner_membership()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
  insert into public.business_members (business_id, user_id, role)
  values (new.id, new.owner_id, 'owner');
  return new;
end;
$$;

create trigger businesses_add_owner
  after insert on public.businesses
  for each row execute function public.add_owner_membership();

create table public.data_uploads (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  kind text not null check (kind in ('sales','inventory')),
  filename text,
  status text not null default 'pending' check (status in ('pending','processing','ready','failed')),
  status_reason text,
  report jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index on public.data_uploads (business_id, kind);

create table public.sales_observations (
  id bigint generated always as identity primary key,
  business_id uuid not null references public.businesses(id) on delete cascade,
  upload_id uuid not null references public.data_uploads(id) on delete cascade,
  product text not null,
  observed_on date not null,
  price numeric not null check (price > 0),
  units numeric not null check (units >= 0)
);
create index on public.sales_observations (business_id, product, observed_on);
create index on public.sales_observations (upload_id);

create table public.inventory_observations (
  id bigint generated always as identity primary key,
  business_id uuid not null references public.businesses(id) on delete cascade,
  upload_id uuid not null references public.data_uploads(id) on delete cascade,
  product text not null,
  observed_on date not null,
  stock_on_hand numeric not null check (stock_on_hand >= 0),
  reorder_point numeric check (reorder_point >= 0)
);
create index on public.inventory_observations (business_id, product, observed_on);
create index on public.inventory_observations (upload_id);

create table public.computed_results (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  upload_id uuid references public.data_uploads(id) on delete set null,
  kind text not null check (kind in ('elasticity','forecast','inventory')),
  payload jsonb not null,
  created_at timestamptz not null default now()
);
create index on public.computed_results (business_id, kind, created_at desc);

create table public.ai_insights (
  id uuid primary key default gen_random_uuid(),
  business_id uuid not null references public.businesses(id) on delete cascade,
  scope text not null check (scope in ('initial','data')),
  body text not null,
  model text not null,
  grounding jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index on public.ai_insights (business_id, scope, created_at desc);

-- RLS on everything.
alter table public.businesses enable row level security;
alter table public.business_members enable row level security;
alter table public.data_uploads enable row level security;
alter table public.sales_observations enable row level security;
alter table public.inventory_observations enable row level security;
alter table public.computed_results enable row level security;
alter table public.ai_insights enable row level security;

create policy businesses_select on public.businesses for select to authenticated
  using (public.is_business_member(id));
create policy businesses_insert on public.businesses for insert to authenticated
  with check (owner_id = auth.uid());
create policy businesses_update on public.businesses for update to authenticated
  using (public.is_business_member(id)) with check (public.is_business_member(id));
create policy businesses_delete on public.businesses for delete to authenticated
  using (owner_id = auth.uid());

create policy members_select on public.business_members for select to authenticated
  using (user_id = auth.uid());

create policy uploads_select on public.data_uploads for select to authenticated
  using (public.is_business_member(business_id));
create policy uploads_insert on public.data_uploads for insert to authenticated
  with check (public.is_business_member(business_id));
create policy uploads_delete on public.data_uploads for delete to authenticated
  using (public.is_business_member(business_id));

create policy sales_select on public.sales_observations for select to authenticated
  using (public.is_business_member(business_id));
create policy sales_insert on public.sales_observations for insert to authenticated
  with check (public.is_business_member(business_id));
create policy sales_delete on public.sales_observations for delete to authenticated
  using (public.is_business_member(business_id));

create policy inventory_select on public.inventory_observations for select to authenticated
  using (public.is_business_member(business_id));
create policy inventory_insert on public.inventory_observations for insert to authenticated
  with check (public.is_business_member(business_id));
create policy inventory_delete on public.inventory_observations for delete to authenticated
  using (public.is_business_member(business_id));

-- Computed results and AI insights are written server-side (service role) only.
create policy results_select on public.computed_results for select to authenticated
  using (public.is_business_member(business_id));
create policy insights_select on public.ai_insights for select to authenticated
  using (public.is_business_member(business_id));

-- Explicit grants (new Supabase tables are not auto-granted).
grant select, insert, update, delete on public.businesses to authenticated;
grant select on public.business_members to authenticated;
grant select, insert, delete on public.data_uploads to authenticated;
grant select, insert, delete on public.sales_observations to authenticated;
grant select, insert, delete on public.inventory_observations to authenticated;
grant select on public.computed_results to authenticated;
grant select on public.ai_insights to authenticated;
grant all on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to authenticated, service_role;
revoke execute on function public.add_owner_membership() from public, anon, authenticated;

revoke execute on function public.is_business_member(uuid) from public, anon;
grant execute on function public.is_business_member(uuid) to authenticated, service_role;
