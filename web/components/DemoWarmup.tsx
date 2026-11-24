"use client";
import { useEffect } from "react";
import { wakeApiFromBrowser } from "@/lib/readiness";

/** One wake-up per page mount, not a timer or keep-alive. */
export default function DemoWarmup({ apiOrigin = "" }: { apiOrigin?: string }) {
  useEffect(() => {
    const controller = new AbortController();
    void wakeApiFromBrowser(apiOrigin, controller.signal);
    void fetch("/api/demo-ready", { cache: "no-store", signal: controller.signal }).catch(() => {});
    return () => controller.abort();
  }, [apiOrigin]);
  return null;
}
