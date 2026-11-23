"use server";

import { randomUUID } from "node:crypto";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { staffApi, StaffApiError } from "@/lib/api";
import { positiveId } from "@/lib/input";
import type { Loan } from "@/lib/types";

function responsePath(branchId: number, notice: string): string {
  const status = ["issued", "returned", "invalid", "denied", "conflict", "unavailable"].includes(notice)
    ? notice : "unavailable";
  return `/workspace/${branchId}/circulation?notice=${status}`;
}

function errorNotice(error: unknown): string {
  if (error instanceof StaffApiError) {
    if (error.status === 401 || error.status === 403 || error.status === 404) return "denied";
    if (error.status === 409) return "conflict";
    if (error.status === 422) return "invalid";
  }
  return "unavailable";
}

export async function issueLoan(formData: FormData) {
  const branchId = positiveId(formData.get("branchId"));
  const memberId = positiveId(formData.get("memberId"));
  const copyId = positiveId(formData.get("copyId"));
  if (!branchId) redirect("/workspace");
  if (!memberId || !copyId) redirect(responsePath(branchId, "invalid"));
  let notice = "issued";
  try {
    await staffApi<Loan>("/api/v2/loans/local", {
      body: { branch_id: branchId, member_id: memberId, copy_id: copyId },
      key: randomUUID(),
    });
    revalidatePath(`/workspace/${branchId}`);
    revalidatePath(`/workspace/${branchId}/catalog`);
  } catch (error) {
    notice = errorNotice(error);
  }
  redirect(responsePath(branchId, notice));
}

export async function returnLoan(formData: FormData) {
  const branchId = positiveId(formData.get("branchId"));
  const loanId = positiveId(formData.get("loanId"));
  if (!branchId) redirect("/workspace");
  if (!loanId) redirect(responsePath(branchId, "invalid"));
  const physicalCondition = formData.get("condition");
  if (physicalCondition !== "GOOD" && physicalCondition !== "DAMAGED") {
    redirect(responsePath(branchId, "invalid"));
  }
  let notice = "returned";
  try {
    await staffApi<Loan>(`/api/v2/loans/${loanId}/local-return`, {
      body: { branch_id: branchId, condition: physicalCondition },
    });
    revalidatePath(`/workspace/${branchId}`);
    revalidatePath(`/workspace/${branchId}/catalog`);
  } catch (error) {
    notice = errorNotice(error);
  }
  redirect(responsePath(branchId, notice));
}
