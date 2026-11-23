"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { guestApi } from "@/lib/guest-api";
import { positiveId } from "@/lib/input";
import { StaffApiError } from "@/lib/api";

type LoanResponse = { id: number };
type TransferResponse = { id: number };

function destination(branch: number, code: string, loanId?: number): string {
  const allowed = ["requested", "advanced", "activated", "returned", "invalid", "denied", "conflict", "quota", "unavailable"];
  const notice = allowed.includes(code) ? code : "unavailable";
  const url = new URL(`https://local.invalid/demo/${branch}/transfers`);
  url.searchParams.set("notice", notice);
  if (loanId) url.searchParams.set("loan", String(loanId));
  return url.pathname + url.search;
}

function failure(error: unknown): string {
  if (error instanceof StaffApiError) {
    if (error.status === 403 || error.status === 404) return "denied";
    if (error.status === 409) return "conflict";
    if (error.status === 422) return "invalid";
    if (error.status === 429) return "quota";
  }
  return "unavailable";
}

function refresh(branch: number) {
  revalidatePath(`/demo/${branch}`);
  revalidatePath(`/demo/${branch}/transfers`);
}

export async function requestGuestTransfer(form: FormData): Promise<never> {
  const branch = positiveId(form.get("branch"));
  const destinationBranch = positiveId(form.get("destination"));
  const member = positiveId(form.get("member"));
  const copy = positiveId(form.get("copy"));
  if (!branch) redirect("/demo");
  if (!destinationBranch || destinationBranch === branch || !member || !copy) {
    redirect(destination(branch, "invalid"));
  }
  let target = destination(branch, "unavailable");
  try {
    const loan = await guestApi<LoanResponse>("/api/v2/guest/loans/interlibrary", {
      body: { member_id: member, copy_id: copy, destination_branch_id: destinationBranch },
      key: randomUUID(),
    });
    refresh(branch);
    target = destination(branch, "requested", loan.id);
  } catch (error) {
    target = destination(branch, failure(error));
  }
  redirect(target);
}

export async function advanceGuestTransfer(form: FormData): Promise<never> {
  const branch = positiveId(form.get("branch"));
  const transfer = positiveId(form.get("transfer"));
  const loan = positiveId(form.get("loan"));
  if (!branch) redirect("/demo");
  const next = form.get("next");
  if (!transfer || !["DISPATCHED", "IN_TRANSIT", "RECEIVED"].includes(String(next))) {
    redirect(destination(branch, "invalid"));
  }
  let target = destination(branch, "unavailable");
  try {
    await guestApi<TransferResponse>(`/api/v2/guest/transfers/${transfer}/transitions`, {
      body: { next_status: next },
    });
    refresh(branch);
    target = destination(branch, "advanced", loan ?? undefined);
  } catch (error) {
    target = destination(branch, failure(error));
  }
  redirect(target);
}

export async function activateGuestLoan(form: FormData): Promise<never> {
  const branch = positiveId(form.get("branch"));
  const loan = positiveId(form.get("loan"));
  if (!branch) redirect("/demo");
  if (!loan) redirect(destination(branch, "invalid"));
  let target = destination(branch, "unavailable");
  try {
    await guestApi<LoanResponse>(`/api/v2/guest/loans/${loan}/activate`, { method: "POST" });
    refresh(branch);
    target = destination(branch, "activated", loan);
  } catch (error) {
    target = destination(branch, failure(error));
  }
  redirect(target);
}

export async function returnGuestInterlibraryLoan(form: FormData): Promise<never> {
  const branch = positiveId(form.get("branch"));
  const loan = positiveId(form.get("loan"));
  if (!branch) redirect("/demo");
  if (!loan) redirect(destination(branch, "invalid"));
  const condition = form.get("condition");
  if (condition !== "GOOD" && condition !== "DAMAGED") {
    redirect(destination(branch, "invalid"));
  }
  let target = destination(branch, "unavailable");
  try {
    await guestApi<LoanResponse>(`/api/v2/guest/loans/${loan}/return`, {
      body: { condition },
    });
    refresh(branch);
    target = destination(branch, "returned", loan);
  } catch (error) {
    target = destination(branch, failure(error));
  }
  redirect(target);
}
