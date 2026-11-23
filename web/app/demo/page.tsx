import { redirect } from "next/navigation";
import { guestApi } from "@/lib/guest-api";
import type { GuestProfile } from "@/lib/guest-types";

export const dynamic = "force-dynamic";

export default async function DemoEntrance() {
  const demo = await guestApi<GuestProfile>("/api/v2/guest/me");
  if (!demo.branches[0]) redirect("/");
  redirect(`/demo/${demo.branches[0].branch_id}`);
}
