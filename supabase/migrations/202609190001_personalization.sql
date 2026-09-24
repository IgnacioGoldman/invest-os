create extension if not exists pgcrypto;

create table public.saved_filters (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  expression jsonb not null check (jsonb_typeof(expression) = 'object'),
  sort_key text not null default 'support_1m' check (
    sort_key in ('symbol', 'support_best', 'revenue', 'momentum', 'eps', 'support_1m', 'support_3m', 'support_6m', 'support_1y', 'support_2y', 'support_5y')
  ),
  sort_direction text not null default 'asc' check (sort_direction in ('asc', 'desc')),
  notifications_enabled boolean not null default false,
  last_evaluated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, user_id)
);

create index saved_filters_user_id_idx on public.saved_filters(user_id);

create table public.filter_matches (
  filter_id uuid not null references public.saved_filters(id) on delete cascade,
  ticker text not null check (ticker = upper(ticker) and char_length(ticker) between 1 and 16),
  first_matched_at timestamptz not null default now(),
  last_matched_at timestamptz not null default now(),
  active boolean not null default true,
  primary key (filter_id, ticker)
);

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  filter_id uuid not null,
  ticker text not null check (ticker = upper(ticker) and char_length(ticker) between 1 and 16),
  title text not null check (char_length(title) between 1 and 140),
  body text not null check (char_length(body) between 1 and 300),
  created_at timestamptz not null default now(),
  read_at timestamptz,
  foreign key (filter_id, user_id) references public.saved_filters(id, user_id) on delete cascade
);

create index notifications_user_created_idx on public.notifications(user_id, created_at desc);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if row(new.name, new.expression, new.sort_key, new.sort_direction, new.notifications_enabled)
    is distinct from
    row(old.name, old.expression, old.sort_key, old.sort_direction, old.notifications_enabled)
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

alter table public.saved_filters enable row level security;
alter table public.filter_matches enable row level security;
alter table public.notifications enable row level security;

revoke all on table public.saved_filters from anon, authenticated;
revoke all on table public.filter_matches from anon, authenticated;
revoke all on table public.notifications from anon, authenticated;

grant select, insert, update, delete on table public.saved_filters to authenticated;
grant select, update (read_at) on table public.notifications to authenticated;

create policy "Users read their filters"
on public.saved_filters for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users create their filters"
on public.saved_filters for insert
to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users update their filters"
on public.saved_filters for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "Users delete their filters"
on public.saved_filters for delete
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users read their notifications"
on public.notifications for select
to authenticated
using ((select auth.uid()) = user_id);

create policy "Users mark their notifications read"
on public.notifications for update
to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);
