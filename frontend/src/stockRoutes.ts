import type { OpenDataStockSnapshot } from "./api";

type RoutableStock = Pick<OpenDataStockSnapshot, "ticker" | "name">;

function normalizeLegacySlug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function legacyStockSlug(snapshot: RoutableStock) {
  const rawName = snapshot.name?.trim();
  const firstNamePart = rawName?.split(/[,.]/)[0]?.trim().split(/\s+/)[0];
  const candidate = firstNamePart || snapshot.ticker;
  const slug = candidate.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return slug || snapshot.ticker;
}

export function stockFromRouteSegment<T extends RoutableStock>(stocks: T[], segment: string | null): T | null {
  if (!segment) return null;
  // Tickers take precedence over old company-name links. Keep punctuation so
  // distinct listing symbols cannot collapse into the same route.
  const ticker = segment.toUpperCase();
  const exactMatch = stocks.find((snapshot) => snapshot.ticker.toUpperCase() === ticker);
  if (exactMatch) return exactMatch;

  const normalizedSegment = normalizeLegacySlug(segment);
  if (!normalizedSegment) return null;
  const legacyMatches = stocks.filter((snapshot) => (
    normalizeLegacySlug(legacyStockSlug(snapshot)) === normalizedSegment
  ));
  return legacyMatches.length === 1 ? legacyMatches[0] : null;
}

export function stockRoutePath(snapshot: RoutableStock, basePath: string) {
  const base = basePath.endsWith("/") ? basePath : `${basePath}/`;
  return `${base}${encodeURIComponent(snapshot.ticker)}`;
}
