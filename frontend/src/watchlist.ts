import { requireSupabase } from "./supabase";

export const WATCHLIST_COLORS = [
  { name: "Blue", value: "#58a6ff" },
  { name: "Green", value: "#30d58b" },
  { name: "Amber", value: "#ffbf45" },
  { name: "Purple", value: "#b49aff" },
  { name: "Rose", value: "#ff8ca8" },
] as const;

export type WatchlistGroup = {
  id: string;
  user_id: string;
  name: string;
  color: string;
  position: number;
  collapsed: boolean;
};
export type WatchlistItem = { ticker: string; group_id: string | null; position: number };
export type WatchlistGroupInput = Pick<WatchlistGroup, "name" | "color">;

function check(error: { message: string } | null) {
  if (error) throw new Error(error.message);
}

export async function fetchWatchlistGroups(userId: string) {
  const { data, error } = await requireSupabase().from("watchlist_groups")
    .select("id,user_id,name,color,position,collapsed").eq("user_id", userId)
    .order("position").order("id");
  check(error);
  return (data ?? []) as WatchlistGroup[];
}

export async function createWatchlistGroup(userId: string, input: WatchlistGroupInput, position: number) {
  const { data, error } = await requireSupabase().from("watchlist_groups")
    .insert({ user_id: userId, name: input.name.trim(), color: input.color, position })
    .select("*").single();
  check(error);
  return data as WatchlistGroup;
}

export async function updateWatchlistGroup(userId: string, id: string, input: Partial<WatchlistGroupInput & { collapsed: boolean }>) {
  const { data, error } = await requireSupabase().from("watchlist_groups")
    .update({ ...input, ...(input.name === undefined ? {} : { name: input.name.trim() }) })
    .eq("user_id", userId).eq("id", id).select("*").single();
  check(error);
  return data as WatchlistGroup;
}

export async function deleteWatchlistGroup(userId: string, id: string) {
  const { error } = await requireSupabase().from("watchlist_groups").delete()
    .eq("user_id", userId).eq("id", id);
  check(error);
}

export async function reorderWatchlistGroups(ids: string[]) {
  const { error } = await requireSupabase().rpc("reorder_watchlist_groups", { p_ids: ids });
  check(error);
}

export async function reorderWatchlistItems(items: WatchlistItem[]) {
  const { error } = await requireSupabase().rpc("reorder_watchlist_items", {
    p_items: items.map(({ ticker, group_id }) => ({ ticker, group_id })),
  });
  check(error);
}

// Preserve every other symbol's relative order, including symbols hidden by a filter.
export function moveWatchlistItem(items: WatchlistItem[], ticker: string, groupId: string | null, beforeTicker?: string) {
  const moving = items.find((item) => item.ticker === ticker);
  if (!moving || beforeTicker === ticker) return items;
  const next = [...items].sort((a, b) => a.position - b.position).filter((item) => item.ticker !== ticker);
  let index = beforeTicker ? next.findIndex((item) => item.ticker === beforeTicker && item.group_id === groupId) : -1;
  if (index < 0) {
    index = next.reduce((last, item, i) => item.group_id === groupId ? i + 1 : last, next.length);
  }
  next.splice(index, 0, { ...moving, group_id: groupId });
  return next.map((item, position) => ({ ...item, position }));
}

export function reorderGroupIds(ids: string[], movingId: string, beforeId: string | null) {
  if (movingId === beforeId || !ids.includes(movingId)) return ids;
  const next = ids.filter((id) => id !== movingId);
  const index = beforeId ? next.indexOf(beforeId) : next.length;
  next.splice(index < 0 ? next.length : index, 0, movingId);
  return next;
}
