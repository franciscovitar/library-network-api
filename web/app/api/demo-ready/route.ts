import { waitForApiReady } from "@/lib/api";

export const dynamic = "force-dynamic";
export async function GET() {
  let ready = false;
  try { ready = await waitForApiReady(); } catch { /* No environment details exposed. */ }
  return Response.json({ ready }, { status: ready ? 200 : 503, headers: { "Cache-Control": "no-store" } });
}
