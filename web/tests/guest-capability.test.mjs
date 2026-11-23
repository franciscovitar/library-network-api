import assert from "node:assert/strict";
import test from "node:test";
import { sealGuestId, verifyGuestId } from "../lib/guest-capability.ts";

const secret = "a-synthetic-only-test-secret-at-least-32-characters";
const id = "868f5644-51d1-4a80-a7ad-a2ed9332b8f7";

test("anonymous identity is a tamper-evident, opaque capability", () => {
  const sealed = sealGuestId(id, secret);
  assert.equal(verifyGuestId(sealed, secret), id);
  assert.equal(verifyGuestId(sealed, "a-different-32-character-key-for-test-only"), null);
  assert.equal(verifyGuestId(sealed.replace("868f", "768f"), secret), null);
  assert.equal(verifyGuestId(sealed + ".extra", secret), null);
  assert.equal(verifyGuestId(sealed.slice(0, -2), secret), null);
  assert.equal(verifyGuestId(undefined, secret), null);
});

test("reject weak keys and non-v4 visitor identifiers", () => {
  assert.throws(() => sealGuestId(id, "weak"));
  assert.throws(() => sealGuestId("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", secret));
  assert.equal(verifyGuestId("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.sig", secret), null);
});
