import "server-only";
import { cookies } from "next/headers";
import { sealGuestId, verifyGuestId, GUEST_TTL_SECONDS } from "@/lib/guest-capability";

const COOKIE = process.env.NODE_ENV === "production" ? "__Host-library_guest" : "library_guest";

function cookieSecret(): string {
  const secret = process.env.LIBRARY_GUEST_COOKIE_SECRET;
  if (!secret || secret.length < 32) throw new Error("Anonymous session secret is not configured");
  return secret;
}

export async function guestId(): Promise<string | null> {
  return verifyGuestId((await cookies()).get(COOKIE)?.value, cookieSecret());
}

export async function setGuestId(id: string): Promise<void> {
  (await cookies()).set(COOKIE, sealGuestId(id, cookieSecret()), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: GUEST_TTL_SECONDS,
  });
}
