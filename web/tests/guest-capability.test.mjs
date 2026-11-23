import assert from "node:assert/strict";
import test from "node:test";
import { sealGuestId, verifyGuestId, GUEST_TTL_SECONDS } from "../lib/guest-capability.ts";

const secret = "a-synthetic-only-test-secret-at-least-32-characters";
const id = "868f5644-51d1-4a80-a7ad-a2ed9332b8f7";
const now = 1795460400;

test("anonymous identity uses an HMAC-signed, time-bounded capability", () => {
  const sealed = sealGuestId(id, secret, now);
  assert.equal(verifyGuestId(sealed, secret, now), id);
  assert.equal(verifyGuestId(sealed, "a-different-32-character-key-for-test-only", now), null);
  assert.equal(verifyGuestId(sealed.replace("868f", "768f"), secret, now), null);
  assert.equal(verifyGuestId(sealed + ".extra", secret, now), null);
  assert.equal(verifyGuestId(sealed.slice(0, -2), secret, now), null);
  assert.equal(verifyGuestId(undefined, secret, now), null);
});

test("archived, future and forged issue-time cookies cannot re-create a guest workspace", () => {
  const sealed = sealGuestId(id, secret, now);
  assert.equal(verifyGuestId(sealed, secret, now + GUEST_TTL_SECONDS - 1), id);
  assert.equal(verifyGuestId(sealed, secret, now + GUEST_TTL_SECONDS), null);
  assert.equal(verifyGuestId(sealed, secret, now + 30), id);
  assert.equal(verifyGuestId(sealed, secret, now - 31), null);
  assert.equal(verifyGuestId(sealed.replace(String(now), String(now + 500)), secret, now), null);
  assert.equal(verifyGuestId(sealGuestId(id, secret, now - 99999), secret, now), null);
});

test("reject weak keys and non-v4 visitor identifiers", () => {
  assert.throws(() => sealGuestId(id, "weak", now));
  assert.throws(() => sealGuestId("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", secret, now));
  assert.equal(verifyGuestId("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.1795460400.sig", secret, now), null);
});
