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

test("keeps an individual readiness request alive for a Render Free cold start", async () => {
  let probeTimeout = 0;
  assert.equal(await pollReadiness(async timeoutMs => {
    probeTimeout = timeoutMs;
    return true;
  }, { delayMs: 0 }), true);
  assert.equal(probeTimeout, 75_000);
});

test("waits past one minute for Render Free spin-up plus API startup", async () => {
  const realNow = Date.now;
  let currentTime = 1_000;
  Date.now = () => currentTime;
  try {
    let attempts = 0;
    const ready = await pollReadiness(async () => {
      attempts++;
      currentTime += 3_000;
      return currentTime >= 91_000;
    }, { delayMs: 0 });
    assert.equal(ready, true);
    assert.equal(attempts, 30);
  } finally {
    Date.now = realNow;
  }
});
