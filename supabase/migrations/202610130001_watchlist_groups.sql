create table public.watchlist_groups (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references public.user_profiles(user_id) on delete cascade,
  name text not null check (name = btrim(name) and char_length(name) between 1 and 80),
  color text not null default '#58a6ff' check (color in ('#58a6ff', '#30d58b', '#ffbf45', '#b49aff', '#ff8ca8')),
  position integer not null default 0 check (position >= 0),
  collapsed boolean not null default false,
  created_at timestamptz not null default now()
);

create index watchlist_groups_user_position_idx on public.watchlist_groups(user_id, position, id);

alter table public.watchlist_items
  add column group_id uuid references public.watchlist_groups(id) on delete set null,
  add column position integer not null default 0 check (position >= 0);

with ordered as (
  select user_id, ticker, row_number() over (partition by user_id order by created_at, ticker) - 1 as position
  from public.watchlist_items
)
update public.watchlist_items item set position = ordered.position
from ordered where item.user_id = ordered.user_id and item.ticker = ordered.ticker;

create index watchlist_items_group_position_idx on public.watchlist_items(user_id, group_id, position);

alter table public.watchlist_groups enable row level security;
revoke all on table public.watchlist_groups from anon, authenticated;
grant select, insert, delete on table public.watchlist_groups to authenticated;
grant update (name, color, position, collapsed) on table public.watchlist_groups to authenticated;
grant update (group_id, position) on table public.watchlist_items to authenticated;

create policy "Users read their watchlist groups"
on public.watchlist_groups for select to authenticated
using ((select auth.uid()) = user_id);

create policy "Users create their watchlist groups"
on public.watchlist_groups for insert to authenticated
with check ((select auth.uid()) = user_id);

create policy "Users update their watchlist groups"
on public.watchlist_groups for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

create policy "Users delete their watchlist groups"
on public.watchlist_groups for delete to authenticated
using ((select auth.uid()) = user_id);

drop policy "Users add to their watchlist" on public.watchlist_items;
create policy "Users add to their watchlist"
on public.watchlist_items for insert to authenticated
with check (
  (select auth.uid()) = user_id
  and (group_id is null or exists (
    select 1 from public.watchlist_groups g where g.id = group_id and g.user_id = (select auth.uid())
  ))
);

create policy "Users organize their watchlist"
on public.watchlist_items for update to authenticated
using ((select auth.uid()) = user_id)
with check (
  (select auth.uid()) = user_id
  and (group_id is null or exists (
    select 1 from public.watchlist_groups g where g.id = group_id and g.user_id = (select auth.uid())
  ))
);

-- One transaction per reorder avoids partially saved arrangements.
create function public.reorder_watchlist_groups(p_ids uuid[])
returns void language plpgsql security invoker set search_path = ''
as $$
begin
  if auth.uid() is null then raise exception 'Sign in before editing your watchlist.'; end if;
  if cardinality(p_ids) <> (select count(distinct requested.id) from unnest(p_ids) requested(id))
     or exists (select 1 from unnest(p_ids) requested(id) where not exists (
       select 1 from public.watchlist_groups g where g.id = requested.id and g.user_id = auth.uid()
     )) then
    raise exception 'Invalid watchlist group order.';
  end if;
  update public.watchlist_groups g set position = ordered.ordinality - 1
  from unnest(p_ids) with ordinality ordered(id, ordinality)
  where g.id = ordered.id and g.user_id = auth.uid();
end;
$$;

create function public.reorder_watchlist_items(p_items jsonb)
returns void language plpgsql security invoker set search_path = ''
as $$
begin
  if auth.uid() is null then raise exception 'Sign in before editing your watchlist.'; end if;
  if jsonb_typeof(p_items) is distinct from 'array' then raise exception 'Invalid watchlist order.'; end if;
  if jsonb_array_length(p_items) <> (select count(distinct item ->> 'ticker') from jsonb_array_elements(p_items) item)
     or exists (select 1 from jsonb_array_elements(p_items) item where not exists (
       select 1 from public.watchlist_items w where w.ticker = item ->> 'ticker' and w.user_id = auth.uid()
     )) then
    raise exception 'Invalid watchlist order.';
  end if;
  update public.watchlist_items w
  set group_id = (ordered.item ->> 'group_id')::uuid, position = ordered.ordinality - 1
  from jsonb_array_elements(p_items) with ordinality ordered(item, ordinality)
  where w.ticker = ordered.item ->> 'ticker' and w.user_id = auth.uid();
end;
$$;

revoke all on function public.reorder_watchlist_groups(uuid[]) from public, anon;
revoke all on function public.reorder_watchlist_items(jsonb) from public, anon;
grant execute on function public.reorder_watchlist_groups(uuid[]) to authenticated;
grant execute on function public.reorder_watchlist_items(jsonb) to authenticated;

alter table public.saved_filters drop constraint if exists saved_filters_sort_key_check;
alter table public.saved_filters add constraint saved_filters_sort_key_check check (
  sort_key in ('watchlist_order', 'symbol', 'support_best', 'revenue', 'momentum', 'eps', 'fcf_margin',
    'valuation', 'forward_pe', 'upcoming_earnings', 'support_1m', 'support_3m', 'support_6m', 'support_1y', 'support_2y', 'support_5y')
);
