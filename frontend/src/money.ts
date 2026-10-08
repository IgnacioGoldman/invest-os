import { ensureUserProfile } from "./personalization";
import { requireSupabase } from "./supabase";

export const MONEY_CURRENCIES = ["EUR", "USD", "SEK"] as const;
export type MoneyCurrency = typeof MONEY_CURRENCIES[number];
export type MoneyStatus = "invested" | "uninvested";
export type MoneyInput = { amount: number; currency: MoneyCurrency; source: string; status: MoneyStatus };
export type MoneyEntry = MoneyInput & { id: string; user_id: string; created_at: string };
export type ExchangeRates = { date: string; rates: Record<MoneyCurrency, number> };

export function parseMoneyAmount(value: string): number | null {
  const normalized = value.trim().replace(/\s/g, "").replace(",", ".");
  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) return null;
  const amount = Number(normalized);
  return Number.isFinite(amount) && amount >= 0 && amount < 1e12 ? amount : null;
}

function validateInput(input: MoneyInput) {
  if (!Number.isFinite(input.amount) || input.amount < 0 || input.amount >= 1e12
    || input.amount !== Number(input.amount.toFixed(2))) {
    throw new Error("Enter a valid amount with up to two decimal places.");
  }
  if (!MONEY_CURRENCIES.includes(input.currency)) throw new Error("Choose EUR, USD or SEK.");
  if (!["invested", "uninvested"].includes(input.status)) throw new Error("Choose invested or uninvested.");
  const source = input.source.trim();
  if (!source || source.length > 80) throw new Error("Enter a source, up to 80 characters.");
  return { ...input, source };
}

export async function fetchMoneyEntries(userId: string): Promise<MoneyEntry[]> {
  const { data, error } = await requireSupabase().from("money_entries")
    .select("*").eq("user_id", userId).order("created_at").order("id");
  if (error) throw new Error(error.message);
  return (data ?? []) as MoneyEntry[];
}

export async function saveMoneyEntry(userId: string, input: MoneyInput, id?: string): Promise<MoneyEntry> {
  const payload = { ...validateInput(input), user_id: userId };
  await ensureUserProfile(userId);
  const table = requireSupabase().from("money_entries");
  const query = id ? table.update(payload).eq("id", id).eq("user_id", userId) : table.insert(payload);
  const { data, error } = await query.select("*").single();
  if (error) throw new Error(error.message);
  return data as MoneyEntry;
}

export async function deleteMoneyEntry(userId: string, id: string) {
  const { data, error } = await requireSupabase().from("money_entries").delete()
    .eq("id", id).eq("user_id", userId).select("id").single();
  if (error) throw new Error(error.message);
  if (!data) throw new Error("This amount could not be deleted. Try refreshing.");
}

let cachedRates: { data: ExchangeRates; fetchedAt: number } | null = null;

export async function fetchMoneyExchangeRates(): Promise<ExchangeRates> {
  if (cachedRates && Date.now() - cachedRates.fetchedAt < 3600000) return cachedRates.data;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    // Only public currency pairs are sent; account balances stay in Supabase.
    const response = await fetch("https://api.frankfurter.dev/v2/providers/ecb/rates?base=EUR&quotes=USD,SEK", {
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("Exchange rates are unavailable.");
    const rows: Array<{ date: string; base: string; quote: string; rate: number }> = await response.json();
    const usd = rows.find((row) => row.base === "EUR" && row.quote === "USD");
    const sek = rows.find((row) => row.base === "EUR" && row.quote === "SEK");
    if (!usd || !sek || usd.date !== sek.date || !/^\d{4}-\d{2}-\d{2}$/.test(usd.date)
      || !Number.isFinite(usd.rate) || usd.rate <= 0 || !Number.isFinite(sek.rate) || sek.rate <= 0) {
      throw new Error("Exchange rates are incomplete.");
    }
    const data: ExchangeRates = { date: usd.date, rates: { EUR: 1, USD: usd.rate, SEK: sek.rate } };
    cachedRates = { data, fetchedAt: Date.now() };
    return data;
  } finally {
    clearTimeout(timeout);
  }
}

export function moneyTotals(entries: MoneyInput[], currency: MoneyCurrency, rates: ExchangeRates | null) {
  let invested = 0;
  let uninvested = 0;
  for (const entry of entries) {
    if (entry.currency !== currency && !rates) return null;
    const converted = entry.currency === currency ? entry.amount
      : entry.amount / rates!.rates[entry.currency] * rates!.rates[currency];
    if (entry.status === "invested") invested += converted;
    else uninvested += converted;
  }
  return { invested, uninvested, total: invested + uninvested };
}

export function formatMoney(amount: number, currency: MoneyCurrency) {
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(amount)} ${currency}`;
}
