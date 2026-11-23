import assert from "node:assert/strict";
import test from "node:test";

import { evaluateQaGate } from "../lib/qa-gate.ts";

const settings = { username: "qa-reviewer", password: "a-long-test-password" };
const basic = (username, password) =>
  `Basic ${Buffer.from(`${username}:${password}`, "utf8").toString("base64")}`;

test("fails closed when credentials are missing or invalid", () => {
  assert.equal(evaluateQaGate(null, {}), "misconfigured");
  assert.equal(evaluateQaGate(null, { username: settings.username }), "misconfigured");
  assert.equal(evaluateQaGate(null, { username: "qa:reviewer", password: "secret" }), "misconfigured");
});

test("challenges missing, malformed, and incorrect authorization", () => {
  assert.equal(evaluateQaGate(null, settings), "challenge");
  assert.equal(evaluateQaGate("Bearer token", settings), "challenge");
  assert.equal(evaluateQaGate(basic(settings.username, "wrong-password"), settings), "challenge");
});

test("allows only the exact configured Basic credential", () => {
  assert.equal(evaluateQaGate(basic(settings.username, settings.password), settings), "allow");
  assert.equal(evaluateQaGate(basic("other-reviewer", settings.password), settings), "challenge");
});

test("supports UTF-8 credentials and colons in the password", () => {
  const utf8 = { username: "qa-revisor", password: "contraseña:segura" };
  assert.equal(evaluateQaGate(basic(utf8.username, utf8.password), utf8), "allow");
});
