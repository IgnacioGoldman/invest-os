alter table public.saved_filters
drop constraint if exists saved_filters_sort_key_check;

alter table public.saved_filters
add constraint saved_filters_sort_key_check
check (
  sort_key in (
    'symbol',
    'support_best',
    'revenue',
    'momentum',
    'eps',
    'fcf_margin',
    'valuation',
    'support_1m',
    'support_3m',
    'support_6m',
    'support_1y',
    'support_2y',
    'support_5y'
  )
);
