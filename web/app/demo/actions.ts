"use server";

import { randomUUID } from "node:crypto";
import { redirect } from "next/navigation";
import { serviceApi, StaffApiError } from "@/lib/api";
import { guestId, setGuestId } from "@/lib/guest-session";
import type { GuestProfile } from "@/lib/guest-types";

export async function enterDemo() {
  let id = await guestId();
  if (!id) id = randomUUID();
  try {
    await serviceApi<GuestProfile>(`guest:${id}`, "/api/v2/guest/start", { method: "POST" });
  } catch (error) {
    if (!(error instanceof StaffApiError) || error.status !== 410) throw error;
    id = randomUUID();
    await serviceApi<GuestProfile>(`guest:${id}`, "/api/v2/guest/start", { method: "POST" });
  }
  await setGuestId(id);
  redirect("/demo");
}
