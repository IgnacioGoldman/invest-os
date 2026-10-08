create table public.money_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.user_profiles(user_id) on delete cascade,
  amount numeric(14, 2) not null check (amount >= 0 and amount < 1000000000000),
  currency text not null check (currency in ('USD', 'EUR', 'SEK')),
  source text not null check (source = btrim(source) and char_length(source) between 1 and 80),
  status text not null check (status in ('invested', 'uninvested')),
  created_at timestamptz not null default now()
);

create index money_entries_user_created_idx on public.money_entries(user_id, created_at, id);

alter table public.money_entries enable row level security;
revoke all on table public.money_entries from anon, authenticated;
grant select, insert, update, delete on table public.money_entries to authenticated;

create policy "Users read their money"
on public.money_entries for select to authenticated
using ((select auth.uid()) = user_id);

create policy "Users add their money"
on public.money_entries for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users update their money"
on public.money_entries for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "Users delete their money"
on public.money_entries for delete to authenticated
using ((select auth.uid()) = user_id);
