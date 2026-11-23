import assert from "node:assert/strict";
import test from "node:test";
import { positiveId, boundedSearch } from "../lib/input.ts";
import { feedback } from "../lib/navigation.ts";

test("positive IDs reject negative, decimal, NaN and path injection", () => {
  for (const value of ["", "0", "-1", "1.5", "1e3", "../5", "1/2", " 5", "abc", null]) {
    assert.equal(positiveId(value), null);
  }
  assert.equal(positiveId("1"), 1);
  assert.equal(positiveId("9007199254740991"), 9007199254740991);
  assert.equal(positiveId("9007199254740992"), null);
});

test("search is trimmed and limited before reaching the API", () => {
  assert.equal(boundedSearch("   libro nuevo   "), "libro nuevo");
  assert.equal(boundedSearch("1234567890", 4), "1234");
  assert.equal(boundedSearch({}), "");
});

test("only known feedback codes can be displayed after redirects", () => {
  assert.equal(feedback("issued")?.tone, "success");
  assert.equal(feedback("denied")?.tone, "error");
  assert.equal(feedback("<script>alert(1)</script>"), null);
});
