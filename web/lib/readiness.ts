/** One visitor-driven, read-only request that asks Render Free to wake the API. */
export async function wakeApiFromBrowser(
  origin: string,
  signal?: AbortSignal,
  fetcher: typeof fetch = fetch,
): Promise<void> {
  try {
    const parsed = new URL(origin);
    if (parsed.protocol !== "https:" || parsed.pathname !== "/" || parsed.search || parsed.hash) return;
    await fetcher(parsed.origin + "/ready", {
      method: "GET",
      mode: "no-cors",
      credentials: "omit",
      cache: "no-store",
      signal,
    });
  } catch {
    // This is only a wake-up hint; the server-side readiness check decides when entry can proceed.
  }
}

/** Only probes the public, read-only readiness endpoint. Never retries a mutation. */
export async function probeReady(origin: string, timeoutMs: number, fetcher: typeof fetch = fetch): Promise<boolean> {
  try {
    const response = await fetcher(origin + "/ready", {
      cache: "no-store", redirect: "error", headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) return false;
    const data: unknown = await response.json();
    return !!data && typeof data === "object" && "status" in data && data.status === "ready";
  } catch { return false; }
}

export async function pollReadiness(
  probe: (timeoutMs: number) => Promise<boolean>,
  // Render Free spin-up can take about a minute; the API then applies DB migrations before it can answer.
  // Keep each read-only readiness request alive long enough for one cold start; do not add a keep-alive.
  { budgetMs = 150_000, maxAttempts = 51, delayMs = 3_000 } = {},
): Promise<boolean> {
  const deadline = Date.now() + budgetMs;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    if (await probe(Math.max(1, Math.min(75_000, remaining)))) return true;
    const pause = Math.min(delayMs, deadline - Date.now());
    if (attempt + 1 < maxAttempts && pause > 0) await new Promise(resolve => setTimeout(resolve, pause));
  }
  return false;
}
