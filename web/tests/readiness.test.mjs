import assert from "node:assert/strict";
import test from "node:test";
import { probeReady, pollReadiness } from "../lib/readiness.ts";

test("a loading page or gateway error is not readiness", async () => {
  for (const response of [
    new Response("<html>Waking up</html>", { status: 200 }),
    new Response("Bad gateway", { status: 502 }),
    Response.json({ status: "not-ready" }),
  ]) assert.equal(await probeReady("https://example.invalid", 1000, async () => response), false);
  assert.equal(await probeReady("https://example.invalid", 1000, async (url, options) => {
    assert.equal(url, "https://example.invalid/ready");
    assert.equal(options.method, undefined);
    assert.equal(options.cache, "no-store");
    return Response.json({ status: "ready" });
  }), true);
});

test("polling recovers from transient failures and is bounded", async () => {
  let attempts = 0;
  assert.equal(await pollReadiness(async () => ++attempts === 3, { delayMs: 0, maxAttempts: 4 }), true);
  assert.equal(attempts, 3);
  attempts = 0;
  assert.equal(await pollReadiness(async () => { attempts++; return false; }, { delayMs: 0, maxAttempts: 3 }), false);
  assert.equal(attempts, 3);
});
