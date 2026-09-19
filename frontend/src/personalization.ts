import type { FilterExpression, SortDirection, SortKey } from "./components/MobileStockExplorer";
import { requireSupabase } from "./supabase";

export const PULLBACK_FILTER_KEY = "builtin:pullback";
export const SUPPORT_FILTER_KEY = "builtin:support";

export function savedFilterKey(filterId: string) {
  return `saved:${filterId}`;
}

export type SavedFilter = {
  id: string;
  user_id: string;
  name: string;
  expression: FilterExpression;
  sort_key: SortKey;
  sort_direction: SortDirection;
  created_at: string;
  updated_at: string;
};

export type FilterMatchEvent = {
  filter_key: string;
  ticker: string;
  matched_on: string;
};

export type SaveFilterInput = {
  id?: string;
  userId: string;
  name: string;
  expression: FilterExpression;
  sortKey: SortKey;
  sortDirection: SortDirection;
};

function throwIfError(error: { message: string } | null) {
  if (error) throw new Error(error.message);
}

export async function ensureUserProfile(userId: string) {
  const { error } = await requireSupabase()
    .from("user_profiles")
    .upsert({ user_id: userId }, { onConflict: "user_id", ignoreDuplicates: true });
  throwIfError(error);
}

export async function fetchSavedFilters(userId: string) {
  const { data, error } = await requireSupabase()
    .from("saved_filters")
    .select("*")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false });
  throwIfError(error);
  return (data ?? []) as SavedFilter[];
}

export async function saveFilter(input: SaveFilterInput) {
  const payload = {
    user_id: input.userId,
    name: input.name.trim(),
    expression: input.expression,
    sort_key: input.sortKey,
    sort_direction: input.sortDirection,
  };
  const query = input.id
    ? requireSupabase().from("saved_filters").update(payload).eq("id", input.id)
    : requireSupabase().from("saved_filters").insert(payload);
  const { data, error } = await query.select("*").single();
  throwIfError(error);
  return data as SavedFilter;
}

export async function deleteSavedFilter(filterId: string) {
  const { error } = await requireSupabase().from("saved_filters").delete().eq("id", filterId);
  throwIfError(error);
}

export async function fetchWatchlist(userId: string) {
  const { data, error } = await requireSupabase()
    .from("watchlist_items")
    .select("ticker")
    .eq("user_id", userId)
    .order("created_at", { ascending: true });
  throwIfError(error);
  return (data ?? []).map((item) => String(item.ticker));
}

export async function addWatchlistItem(userId: string, ticker: string) {
  const symbol = ticker.toUpperCase();
  const { error } = await requireSupabase()
    .from("watchlist_items")
    .upsert({ user_id: userId, ticker: symbol }, { onConflict: "user_id,ticker", ignoreDuplicates: true });
  throwIfError(error);
  return symbol;
}

export async function removeWatchlistItem(userId: string, ticker: string) {
  const symbol = ticker.toUpperCase();
  const { error } = await requireSupabase()
    .from("watchlist_items")
    .delete()
    .eq("user_id", userId)
    .eq("ticker", symbol);
  throwIfError(error);
}

export async function fetchFilterMatchEvents(userId: string, matchedOn: string) {
  const { data, error } = await requireSupabase()
    .from("filter_match_events")
    .select("filter_key,ticker,matched_on")
    .eq("user_id", userId)
    .eq("matched_on", matchedOn);
  throwIfError(error);
  return (data ?? []) as FilterMatchEvent[];
}
