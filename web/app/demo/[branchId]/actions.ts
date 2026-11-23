"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { guestApi } from "@/lib/guest-api";
import { positiveId } from "@/lib/input";
import { StaffApiError } from "@/lib/api";
import type { Loan } from "@/lib/types";

function notice(error: unknown) {
  if (error instanceof StaffApiError) {
    if (error.status === 403 || error.status === 404) return "denied";
    if (error.status === 409) return "conflict";
    if (error.status === 429) return "quota";
  }
  return "unavailable";
}

export async function guestIssue(form: FormData) {
  const branch = positiveId(form.get("branch"));
  const member = positiveId(form.get("member"));
  const copy = positiveId(form.get("copy"));
  if (!branch) redirect("/demo");
  if (!member || !copy) redirect(`/demo/${branch}?notice=invalid`);
  let to = `/demo/${branch}?notice=unavailable`;
  try {
    const loan = await guestApi<Loan>("/api/v2/guest/loans/local", {
      body: { branch_id: branch, member_id: member, copy_id: copy },
      key: randomUUID(),
    });
    revalidatePath(`/demo/${branch}`);
    to = `/demo/${branch}?notice=issued&loan=${loan.id}`;
  } catch (error) { to = `/demo/${branch}?notice=${notice(error)}`; }
  redirect(to);
}

export async function guestReturn(form: FormData) {
  const branch = positiveId(form.get("branch"));
  const loan = positiveId(form.get("loan"));
  if (!branch) redirect("/demo");
  if (!loan) redirect(`/demo/${branch}?notice=invalid`);
  let to = `/demo/${branch}?notice=unavailable`;
  try {
    await guestApi<Loan>(`/api/v2/guest/loans/${loan}/local-return`, {
      body: { branch_id: branch, condition: "GOOD" },
    });
    revalidatePath(`/demo/${branch}`);
    to = `/demo/${branch}?notice=returned&loan=${loan}`;
  } catch (error) { to = `/demo/${branch}?notice=${notice(error)}`; }
  redirect(to);
}
