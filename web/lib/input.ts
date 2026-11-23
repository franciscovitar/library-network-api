/** Reject ambiguous/overflowing IDs before constructing API paths. */
export function positiveId(value: unknown): number | null {
  if (typeof value !== "string" || !/^[1-9][0-9]{0,14}$/.test(value)) return null;
  const number = Number(value);
  return Number.isSafeInteger(number) && number > 0 ? number : null;
}

export function boundedSearch(value: unknown, maxLength = 100): string {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, maxLength);
}
