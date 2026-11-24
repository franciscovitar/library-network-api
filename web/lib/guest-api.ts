import { redirect } from "next/navigation";
import { serviceApi, StaffApiError, waitForApiReady } from "@/lib/api";
import { guestId } from "@/lib/guest-session";

export async function guestApi<T>(
  path: string,
  init?: { body?: object; key?: string; method?: "GET" | "POST" },
): Promise<T> {
  const id = await guestId();
  if (!id) redirect("/");
  try {
    return await serviceApi<T>(`guest:${id}`, path, init);
  } catch (error) {
    const isRead = (init?.method ?? (init?.body ? "POST" : "GET")) === "GET";
    if (!isRead || !(error instanceof StaffApiError) || ![502, 503, 504].includes(error.status)) throw error;
    if (!await waitForApiReady()) throw error;
    return serviceApi<T>(`guest:${id}`, path, init);
  }
}
