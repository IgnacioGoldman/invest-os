const currencyFormatters = new Map<string, Intl.NumberFormat | null>();
const numberFormatters = new Map<string, Intl.NumberFormat>();
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});
export const HIDDEN_ABSOLUTE_VALUE = "••••";

function getNumberFormatter(maximumFractionDigits: number, minimumFractionDigits = 0) {
  const key = `${minimumFractionDigits}:${maximumFractionDigits}`;
  const cached = numberFormatters.get(key);
  if (cached) {
    return cached;
  }
  const formatter = new Intl.NumberFormat(undefined, { minimumFractionDigits, maximumFractionDigits });
  numberFormatters.set(key, formatter);
  return formatter;
}

function getCurrencyFormatter(currency: string) {
  const key = currency.toUpperCase();
  if (currencyFormatters.has(key)) {
    return currencyFormatters.get(key) ?? null;
  }
  try {
    const formatter = new Intl.NumberFormat(undefined, { style: "currency", currency: key });
    currencyFormatters.set(key, formatter);
    return formatter;
  } catch {
    currencyFormatters.set(key, null);
    return null;
  }
}

export function formatMoney(value: number, currency: string) {
  const formatter = getCurrencyFormatter(currency);
  if (formatter) {
    return formatter.format(value);
  }
  return `${getNumberFormatter(8).format(value)} ${currency}`;
}

export function formatMoneyPrivacy(value: number, currency: string, hideAbsoluteValues = false) {
  return hideAbsoluteValues ? HIDDEN_ABSOLUTE_VALUE : formatMoney(value, currency);
}

export function formatNumber(value: number) {
  return getNumberFormatter(6).format(value);
}

export function formatDateTime(value?: string | null) {
  if (!value) {
    return "-";
  }
  return dateTimeFormatter.format(new Date(value));
}
