drop table if exists public.notifications;
drop table if exists public.filter_matches;

drop trigger if exists saved_filters_set_updated_at on public.saved_filters;
alter table public.saved_filters drop column if exists notifications_enabled;
alter table public.saved_filters drop column if exists last_evaluated_at;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if row(new.name, new.expression, new.sort_key, new.sort_direction)
    is distinct from
    row(old.name, old.expression, old.sort_key, old.sort_direction)
  then
    new.updated_at = now();
  else
    new.updated_at = old.updated_at;
  end if;
  return new;
end;
$$;

create trigger saved_filters_set_updated_at
before update on public.saved_filters
for each row execute function public.set_updated_at();

create table public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

insert into public.user_profiles (user_id)
select id from auth.users
on conflict (user_id) do nothing;

create table public.watchlist_items (
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  ticker text not null check (ticker = upper(ticker) and char_length(ticker) between 1 and 16),
  created_at timestamptz not null default now(),
  primary key (user_id, ticker)
);

create table public.filter_evaluations (
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  filter_key text not null check (char_length(filter_key) between 1 and 120),
  last_evaluated_at timestamptz not null default now(),
  primary key (user_id, filter_key)
);

create table public.filter_match_state (
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  filter_key text not null check (char_length(filter_key) between 1 and 120),
  ticker text not null check (ticker = upper(ticker) and char_length(ticker) between 1 and 16),
  first_matched_at timestamptz not null default now(),
  last_matched_at timestamptz not null default now(),
  active boolean not null default true,
  primary key (user_id, filter_key, ticker)
);

create table public.filter_match_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(user_id) on delete cascade,
  filter_key text not null check (char_length(filter_key) between 1 and 120),
  ticker text not null check (ticker = upper(ticker) and char_length(ticker) between 1 and 16),
  matched_on date not null,
  created_at timestamptz not null default now(),
  unique (user_id, filter_key, ticker, matched_on)
);

create index filter_match_events_user_day_idx
on public.filter_match_events(user_id, matched_on desc);

create or replace function public.handle_new_user_profile()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.user_profiles (user_id) values (new.id)
  on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists create_user_profile on auth.users;
create trigger create_user_profile
after insert on auth.users
for each row execute function public.handle_new_user_profile();

create or replace function public.cleanup_saved_filter_tracking()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  delete from public.filter_evaluations where user_id = old.user_id and filter_key = 'saved:' || old.id::text;
  delete from public.filter_match_state where user_id = old.user_id and filter_key = 'saved:' || old.id::text;
  delete from public.filter_match_events where user_id = old.user_id and filter_key = 'saved:' || old.id::text;
  return old;
end;
$$;

drop trigger if exists cleanup_saved_filter_tracking on public.saved_filters;
create trigger cleanup_saved_filter_tracking
after delete on public.saved_filters
for each row execute function public.cleanup_saved_filter_tracking();

alter table public.user_profiles enable row level security;
alter table public.watchlist_items enable row level security;
alter table public.filter_evaluations enable row level security;
alter table public.filter_match_state enable row level security;
alter table public.filter_match_events enable row level security;

revoke all on table public.user_profiles from anon, authenticated;
revoke all on table public.watchlist_items from anon, authenticated;
revoke all on table public.filter_evaluations from anon, authenticated;
revoke all on table public.filter_match_state from anon, authenticated;
revoke all on table public.filter_match_events from anon, authenticated;

grant select, insert on table public.user_profiles to authenticated;
grant select, insert, delete on table public.watchlist_items to authenticated;
grant select on table public.filter_match_events to authenticated;

create policy "Users read their profile"
on public.user_profiles for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users create their profile"
on public.user_profiles for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users read their watchlist"
on public.watchlist_items for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users add to their watchlist"
on public.watchlist_items for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users remove from their watchlist"
on public.watchlist_items for delete
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users read their daily filter matches"
on public.filter_match_events for select
to authenticated
using ((select auth.uid()) = user_id);
