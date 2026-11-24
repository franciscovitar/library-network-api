"use client";
import { useFormStatus } from "react-dom";
import type { ReactNode } from "react";
export default function PendingButton({ children, className, disabled = false, pendingLabel = "Procesando…" }: { children: ReactNode; className: string; disabled?: boolean; pendingLabel?: string }) {
  const { pending } = useFormStatus();
  return <button type="submit" className={className} disabled={disabled || pending} aria-busy={pending}>{pending ? pendingLabel : children}</button>;
}
