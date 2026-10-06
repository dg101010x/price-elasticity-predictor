-- Precise business location for the geospatial engine (LAEE spec sections 5-7: markets are not ZIP codes).

alter table public.businesses
  add column country_code text check (country_code ~ '^[A-Z]{2}$'),
  add column address text check (address is null or char_length(address) <= 200),
  add column latitude double precision check (latitude between -90 and 90),
  add column longitude double precision check (longitude between -180 and 180),
  add column location_accuracy_m double precision check (location_accuracy_m >= 0),
  add column location_source text check (location_source in ('device', 'geocoded', 'manual'));

alter table public.businesses
  add constraint businesses_coordinates_paired check ((latitude is null) = (longitude is null)),
  add constraint businesses_location_source_matches check ((location_source is null) = (latitude is null)),
  add constraint businesses_description_not_blank check (btrim(description) <> '');

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

revoke execute on function public.set_updated_at() from public, anon, authenticated;

create trigger businesses_set_updated_at
  before update on public.businesses
  for each row execute function public.set_updated_at();
