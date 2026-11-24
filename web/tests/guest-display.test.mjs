import assert from "node:assert/strict";
import test from "node:test";
import { memberLabel, copyLabel, loanStatus } from "../lib/guest-display.ts";
test("synthetic labels are stable and hide internal hashes", () => {
  assert.equal(memberLabel("D-01234567890123456789-M01"), "Sofía Martínez · Socio 01");
  assert.equal(memberLabel("D-other-M01"), "Sofía Martínez · Socio 01");
  assert.equal(memberLabel("unknown-hash"), "Socio de prueba");
  assert.equal(copyLabel("D-01234567890123456789-C04"), "Ejemplar 04");
  assert.equal(loanStatus("ACTIVE"), "Activo");
});
