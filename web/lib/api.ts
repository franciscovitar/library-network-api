import { auth } from "@/auth";
import { importPKCS8, SignJWT } from "jose";
import { redirect } from "next/navigation";
import { pollReadiness, probeReady } from "@/lib/readiness";

/** Only server components/actions call this module; no bearer or key reaches a browser. */
export class StaffApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "StaffApiError";
  }
}

function apiOrigin(): string {
  const raw = process.env.LIBRARY_API_URL;
  if (!raw) throw new StaffApiError(503, "El servicio todavía no está configurado.");
  let parsed: URL;
  try { parsed = new URL(raw); }
  catch { throw new StaffApiError(503, "Dirección de API inválida."); }
  const local = ["localhost", "127.0.0.1", "::1", "[::1]"].includes(parsed.hostname);
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && local && process.env.NODE_ENV !== "production")) {
    throw new StaffApiError(503, "La conexión segura al servicio no está configurada.");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash || (parsed.pathname !== "/" && parsed.pathname !== "")) {
    throw new StaffApiError(503, "La configuración de API no es válida.");
  }
  return parsed.origin;
}

// Coalesce concurrent warm-up requests within this server process. No periodic keep-alive.
let waking: Promise<boolean> | undefined;
export function waitForApiReady(): Promise<boolean> {
  if (!waking) {
    const origin = apiOrigin();
    waking = pollReadiness(timeout => probeReady(origin, timeout)).finally(() => { waking = undefined; });
  }
  return waking;
}

async function signedServiceToken(subject: string): Promise<string> {
  const pem = process.env.LIBRARY_API_SIGNING_KEY_PKCS8?.replace(/\\n/g, "\n");
  const kid = process.env.LIBRARY_API_SIGNING_KID;
  const iss = process.env.LIBRARY_JWT_ISSUER;
  const aud = process.env.LIBRARY_JWT_AUDIENCE;
  if (!pem || !kid || !iss || !aud || !/^[A-Za-z0-9._-]{1,128}$/.test(kid)) {
    throw new StaffApiError(503, "La autenticación de servicio aún no está configurada.");
  }
  const key = await importPKCS8(pem, "RS256");
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({})
    .setProtectedHeader({ alg: "RS256", kid })
    .setSubject(subject)
    .setIssuer(iss)
    .setAudience(aud)
    .setIssuedAt(now)
    .setNotBefore(now)
    .setExpirationTime(now + 180)
    .sign(key);
}

export async function staffSubject(): Promise<string> {
  const session = await auth();
  const subject = session?.user?.staffSubject;
  if (!subject || !/^github:[0-9]+$/.test(subject)) redirect("/login");
  return subject;
}

export async function serviceApi<T>(
  subject: string,
  path: string,
  init?: { body?: object; key?: string; method?: "GET" | "POST" },
): Promise<T> {
  if (!path.startsWith("/api/v2/") || path.includes("//") || path.includes("..")) {
    throw new StaffApiError(500, "Ruta de API no permitida.");
  }
  const guestPath = path.startsWith("/api/v2/guest/");
  const guestSubject = /^guest:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(subject);
  if ((guestPath && !guestSubject) || (!guestPath && guestSubject) || (!guestSubject && !/^github:[0-9]+$/.test(subject))) {
    throw new StaffApiError(403, "La identidad no tiene acceso a esta API.");
  }
  const bearer = await signedServiceToken(subject);
  const headers: Record<string, string> = {
    Accept: "application/json",
    Authorization: `Bearer ${bearer}`,
  };
  if (init?.body) headers["Content-Type"] = "application/json";
  if (init?.key) headers["Idempotency-Key"] = init.key;
  let response: Response;
  try {
    response = await fetch(apiOrigin() + path, {
      method: init?.method ?? (init?.body ? "POST" : "GET"),
      headers,
      body: init?.body ? JSON.stringify(init.body) : undefined,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(75000),
    });
  } catch {
    throw new StaffApiError(503, "No se pudo conectar con Library Network.");
  }
  if (!response.ok) {
    let code = "";
    try {
      const result: unknown = await response.json();
      if (result && typeof result === "object" && "error" in result) {
        const value = result.error;
        if (value && typeof value === "object" && "code" in value && typeof value.code === "string") {
          code = value.code;
        }
      }
    } catch { /* Error responses need not be JSON. */ }
    const message = response.status === 403 ? "No tenés permiso para esta operación."
      : response.status === 404 ? "No se encontró el recurso solicitado."
      : response.status === 409 ? `La operación no puede completarse: ${code || "estado incompatible"}.`
      : response.status === 401 ? "La sesión del servicio no es válida."
      : "La operación no está disponible en este momento.";
    throw new StaffApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export async function staffApi<T>(path: string, init?: { body?: object; key?: string }): Promise<T> {
  return serviceApi<T>(await staffSubject(), path, init);
}
