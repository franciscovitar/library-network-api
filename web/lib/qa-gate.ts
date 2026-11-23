import { timingSafeEqual } from "node:crypto";

export type QaGateDecision = "allow" | "challenge" | "misconfigured";

const BASIC_AUTH_PATTERN = /^Basic\s+([A-Za-z0-9+/]+={0,2})$/i;

/** Fail closed unless a configured HTTP Basic credential matches exactly. */
export function evaluateQaGate(
  authorization: string | null,
  settings: { username?: string; password?: string },
): QaGateDecision {
  const { username, password } = settings;
  if (!username || username.includes(":") || !password) return "misconfigured";

  const match = authorization?.match(BASIC_AUTH_PATTERN);
  if (!match) return "challenge";

  const supplied = Buffer.from(match[1], "base64");
  const expected = Buffer.from(`${username}:${password}`, "utf8");
  if (supplied.length !== expected.length) return "challenge";
  return timingSafeEqual(supplied, expected) ? "allow" : "challenge";
}
