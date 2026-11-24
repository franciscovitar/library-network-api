import assert from "node:assert/strict";
import test from "node:test";
import { probeReady, pollReadiness, wakeApiFromBrowser } from "../lib/readiness.ts";

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

test("visitor wake request is one credential-free, read-only GET", async () => {
  let request;
  await wakeApiFromBrowser("https://api.example.com/", undefined, async (url, options) => {
    request = { url, options };
    return new Response(null, { status: 503 });
  });
  assert.equal(request.url, "https://api.example.com/ready");
  assert.equal(request.options.method, "GET");
  assert.equal(request.options.mode, "no-cors");
  assert.equal(request.options.credentials, "omit");
  assert.equal(request.options.cache, "no-store");
  assert.equal(request.options.headers, undefined);
});

test("visitor wake is limited to HTTPS root origins and never blocks entry", async () => {
  let calls = 0;
  await wakeApiFromBrowser("https://api.example.com", undefined, async () => {
    calls++;
    throw new Error("network unavailable");
  });
  await wakeApiFromBrowser("http://api.example.com", undefined, async () => {
    calls++;
    return new Response();
  });
  await wakeApiFromBrowser("https://api.example.com/extra", undefined, async () => {
    calls++;
    return new Response();
  });
  assert.equal(calls, 1);
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
