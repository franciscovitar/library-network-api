import { createHmac, timingSafeEqual } from "node:crypto";

// The server must not reactivate a workspace using an old stolen/archived cookie.
export const GUEST_TTL_SECONDS = 24 * 60 * 60;
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ISSUE_TIME = /^[1-9][0-9]{9,11}$/;

export function sealGuestId(
  id: string,
  secret: string,
  issuedAt = Math.floor(Date.now() / 1000),
): string {
  if (!UUID_V4.test(id) || secret.length < 32 ||
      !Number.isSafeInteger(issuedAt) || issuedAt < 1_000_000_000) {
    throw new Error("Guest capability misconfigured");
  }
  const payload = `${id}.${issuedAt}`;
  return `${payload}.${createHmac("sha256", secret).update(payload).digest("base64url")}`;
}

export function verifyGuestId(
  raw: string | undefined,
  secret: string,
  now = Math.floor(Date.now() / 1000),
): string | null {
  if (!raw || secret.length < 32 || raw.length > 180) return null;
  const [id, issued, signature, extra] = raw.split(".");
  if (extra !== undefined || !id || !issued || !signature ||
      !UUID_V4.test(id) || !ISSUE_TIME.test(issued)) return null;
  const issuedAt = Number(issued);
  if (!Number.isSafeInteger(issuedAt) || !Number.isSafeInteger(now) ||
      issuedAt > now + 30 || now - issuedAt >= GUEST_TTL_SECONDS) return null;
  const expected = createHmac("sha256", secret).update(`${id}.${issued}`).digest();
  let received: Buffer;
  try { received = Buffer.from(signature, "base64url"); }
  catch { return null; }
  return received.length === expected.length && timingSafeEqual(received, expected)
    ? id
    : null;
}
