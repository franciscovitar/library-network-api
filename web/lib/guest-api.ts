import { redirect } from "next/navigation";
import { serviceApi } from "@/lib/api";
import { guestId } from "@/lib/guest-session";

export async function guestApi<T>(
  path: string,
  init?: { body?: object; key?: string; method?: "GET" | "POST" },
): Promise<T> {
  const id = await guestId();
  if (!id) redirect("/");
  return serviceApi<T>(`guest:${id}`, path, init);
}
