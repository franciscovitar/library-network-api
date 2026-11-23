import { createHmac, timingSafeEqual } from "node:crypto";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function sealGuestId(id: string, secret: string): string {
  if (!UUID_V4.test(id) || secret.length < 32) throw new Error("Guest capability misconfigured");
  return `${id}.${createHmac("sha256", secret).update(id).digest("base64url")}`;
}

export function verifyGuestId(raw: string | undefined, secret: string): string | null {
  if (!raw || secret.length < 32 || raw.length > 160) return null;
  const [id, signature, extra] = raw.split(".");
  if (extra !== undefined || !id || !signature || !UUID_V4.test(id)) return null;
  const expected = createHmac("sha256", secret).update(id).digest();
  let provided: Buffer;
  try { provided = Buffer.from(signature, "base64url"); }
  catch { return null; }
  if (provided.length !== expected.length || !timingSafeEqual(provided, expected)) return null;
  return id;
}
