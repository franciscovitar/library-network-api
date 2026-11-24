"use server";

import { randomUUID } from "node:crypto";
import { redirect } from "next/navigation";
import { serviceApi, StaffApiError, waitForApiReady } from "@/lib/api";
import { guestId, setGuestId } from "@/lib/guest-session";
import type { GuestProfile } from "@/lib/guest-types";

export async function enterDemo() {
  let id = await guestId();
  if (!id) id = randomUUID();
  let failure: "unavailable" | "quota" | null = null;
  try {
    if (!await waitForApiReady()) throw new StaffApiError(503, "Servicio iniciando.");
    try {
      await serviceApi<GuestProfile>(`guest:${id}`, "/api/v2/guest/start", { method: "POST" });
    } catch (error) {
      if (!(error instanceof StaffApiError) || error.status !== 410) throw error;
      id = randomUUID();
      await serviceApi<GuestProfile>(`guest:${id}`, "/api/v2/guest/start", { method: "POST" });
    }
  } catch (error) {
    if (!(error instanceof StaffApiError)) throw error;
    failure = error.status === 429 ? "quota" : "unavailable";
  }
  if (failure) redirect(`/?notice=${failure}`);
  await setGuestId(id);
  redirect("/demo");
}

/**
 * Begin a different anonymous, PostgreSQL-backed library.
 * Create the replacement BEFORE changing the browser capability: a capacity
 * error must leave the visitor's existing session intact.
 *
 * This changes the active visitor capability, not the retention policy.
 * Previous records remain until the separately authorized cleanup runs.
 */
export async function restartDemo() {
  const nextId = randomUUID();
  await serviceApi<GuestProfile>(`guest:${nextId}`, "/api/v2/guest/start", { method: "POST" });
  await setGuestId(nextId);
  redirect("/demo");
}
