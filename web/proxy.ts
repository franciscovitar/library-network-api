import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { evaluateQaGate } from "./lib/qa-gate";

/** Protect every page and Server Action; no demo or API-facing route is exempt. */
export function proxy(request: NextRequest) {
  const decision = evaluateQaGate(request.headers.get("authorization"), {
    username: process.env.QA_GATE_USERNAME,
    password: process.env.QA_GATE_PASSWORD,
  });

  if (decision === "allow") return NextResponse.next();

  const headers = new Headers({ "Cache-Control": "no-store" });
  if (decision === "challenge") {
    headers.set("WWW-Authenticate", 'Basic realm="Library Network QA", charset="UTF-8"');
  }

  return new NextResponse(
    decision === "misconfigured" ? "QA access gate is not configured." : "Authentication required.",
    { status: decision === "misconfigured" ? 503 : 401, headers },
  );
}
