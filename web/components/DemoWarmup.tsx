"use client";
import { useEffect } from "react";

/** One warm-up per page mount, not a timer or keep-alive. */
export default function DemoWarmup() {
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/demo-ready", { cache: "no-store", signal: controller.signal }).catch(() => {});
    return () => controller.abort();
  }, []);
  return null;
}
