import type { FilterExpression, SortDirection, SortKey } from "./components/MobileStockExplorer";
import { requireSupabase } from "./supabase";

export type SavedFilter = {
  id: string;
  user_id: string;
  name: string;
  expression: FilterExpression;
  sort_key: SortKey;
  sort_direction: SortDirection;
  notifications_enabled: boolean;
  last_evaluated_at: string | null;
  created_at: string;
  updated_at: string;
};

export type StockNotification = {
  id: string;
  user_id: string;
  filter_id: string;
  ticker: string;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
};

export type SaveFilterInput = {
  id?: string;
  userId: string;
  name: string;
  expression: FilterExpression;
  sortKey: SortKey;
  sortDirection: SortDirection;
  notificationsEnabled: boolean;
};

function throwIfError(error: { message: string } | null) {
  if (error) throw new Error(error.message);
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
    notifications_enabled: input.notificationsEnabled,
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

export async function fetchNotifications(userId: string) {
  const { data, error } = await requireSupabase()
    .from("notifications")
    .select("*")
    .eq("user_id", userId)
    .order("created_at", { ascending: false })
    .limit(50);
  throwIfError(error);
  return (data ?? []) as StockNotification[];
}

export async function markNotificationRead(notificationId: string) {
  const { error } = await requireSupabase()
    .from("notifications")
    .update({ read_at: new Date().toISOString() })
    .eq("id", notificationId);
  throwIfError(error);
}

export async function markAllNotificationsRead(userId: string) {
  const { error } = await requireSupabase()
    .from("notifications")
    .update({ read_at: new Date().toISOString() })
    .eq("user_id", userId)
    .is("read_at", null);
  throwIfError(error);
}
