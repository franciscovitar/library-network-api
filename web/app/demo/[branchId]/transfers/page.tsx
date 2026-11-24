import Link from "next/link";
import { notFound } from "next/navigation";
import { guestApi } from "@/lib/guest-api";
import { positiveId } from "@/lib/input";
import GuestNav from "@/components/GuestNav";
import PendingButton from "@/components/PendingButton";
import { memberLabel, copyLabel } from "@/lib/guest-display";
import type { GuestProfile, GuestCopyPage, GuestMember } from "@/lib/guest-types";
import {
  activateGuestLoan,
  advanceGuestTransfer,
  requestGuestTransfer,
  returnGuestInterlibraryLoan,
} from "./actions";

export const dynamic = "force-dynamic";
export const metadata = { title: "Movimientos entre sucursales" };

type Transfer = {
  id: number;
  direction: "OUTBOUND" | "RETURN";
  status: "PREPARED" | "DISPATCHED" | "IN_TRANSIT" | "RECEIVED";
  origin_branch_id: number;
  destination_branch_id: number;
};
type Loan = {
  id: number;
  kind: "LOCAL" | "INTERLIBRARY";
  copy_id: number;
  member_id: number;
  origin_branch_id: number;
  destination_branch_id: number;
  status: "REQUESTED" | "ACTIVE" | "RETURNING" | "CLOSED";
  transfers: Transfer[];
};

const statusName: Record<string, string> = {
  REQUESTED: "Solicitud registrada",
  ACTIVE: "Préstamo activo",
  RETURNING: "Devolución en camino",
  CLOSED: "Completado",
  PREPARED: "Preparado",
  DISPATCHED: "Despachado",
  IN_TRANSIT: "En tránsito",
  RECEIVED: "Recibido",
};

const step: Record<string, { next: "DISPATCHED" | "IN_TRANSIT" | "RECEIVED"; label: string }> = {
  PREPARED: { next: "DISPATCHED", label: "Confirmar despacho" },
  DISPATCHED: { next: "IN_TRANSIT", label: "Marcar en tránsito" },
  IN_TRANSIT: { next: "RECEIVED", label: "Confirmar recepción" },
};

const noticeTexts: Record<string, string> = {
  requested: "Solicitud registrada: se creó el préstamo y su remito de salida en PostgreSQL.",
  advanced: "Movimiento actualizado y evento de trazabilidad guardado.",
  activated: "El préstamo quedó activo y se calculó su fecha de vencimiento.",
  returned: "Devolución registrada; ahora podés completar el traslado de vuelta.",
  invalid: "Verificá la sucursal, el socio y el ejemplar seleccionado.",
  denied: "No se encontró el recurso o no pertenece a tu biblioteca temporal.",
  conflict: "El estado cambió o intentaste omitir una etapa. Actualizá y volvé a intentar.",
  quota: "Alcanzaste el límite de préstamos de este espacio temporal.",
  unavailable: "No se pudo confirmar la operación. Intentá nuevamente.",
};

export default async function GuestTransfers({
  params, searchParams,
}: {
  params: Promise<{ branchId: string }>;
  searchParams: Promise<{ notice?: string; loan?: string }>;
}) {
  const branch = positiveId((await params).branchId);
  if (!branch) notFound();
  const qs = await searchParams;
  const [profile, members, copies, loans] = await Promise.all([
    guestApi<GuestProfile>("/api/v2/guest/me"),
    guestApi<GuestMember[]>("/api/v2/guest/members"),
    guestApi<GuestCopyPage>(`/api/v2/guest/branches/${branch}/copies`),
    guestApi<Loan[]>("/api/v2/guest/loans?limit=50"),
  ]);
  const current = profile.branches.find((b) => b.branch_id === branch);
  if (!current) notFound();
  const destinations = profile.branches.filter((b) => b.branch_id !== branch);
  const ownAvailable = copies.items.filter((c) => c.status === "AVAILABLE");
  const allTransfers = loans.filter((loan) => loan.kind === "INTERLIBRARY");
  const target = positiveId(qs.loan);
  const shown = target ? allTransfers.filter((l) => l.id === target) : allTransfers.slice(0, 12);
  const notice = qs.notice && Object.hasOwn(noticeTexts, qs.notice) ? noticeTexts[qs.notice] : null;
  const branchName = (id: number) => profile.branches.find((b) => b.branch_id === id)?.name.split("· ").at(-1) ?? "Desconocida";

  const stages = ["PREPARED", "DISPATCHED", "IN_TRANSIT", "RECEIVED"] as const;
  const memberName = (id: number) => { const m = members.find(item => item.id === id); return m ? memberLabel(m.code) : "Socio de prueba"; };
  return (
    <div className="workspace-shell guest-shell">
      <GuestNav profile={profile} branch={branch} transfers/>
      <main className="workspace-main">
        <header className="workspace-header">
          <div className="breadcrumb"><span>Biblioteca temporal</span><span>/</span><strong>{branchName(branch)}</strong></div>
          <span className="role-badge">Sin registro · Datos aislados</span>
        </header>
        <div className="workspace-content">
          <div className="page-heading guest-heading">
            <div>
              <div className="eyebrow">CIRCULACIÓN ENTRE SEDES / OPERACIONES REALES</div>
              <h1>Traslados entre sucursales</h1>
              <p>Enviá un libro a otra sucursal, seguí su recorrido y registrá el regreso cuando el socio lo devuelva.</p>
            </div>
            <Link href={`/demo/${branch}`} className="button button-outline">Volver al resumen ↗</Link>
          </div>
          {notice && <div className={["requested","advanced","activated","returned"].includes(qs.notice ?? "") ? "feedback success" : "feedback error"} role="status">{notice}</div>}
          <nav className="guest-section-links" aria-label="Tareas de traslado"><a href="#solicitar">Nuevo traslado</a><a href="#seguimiento">Ver seguimiento ({allTransfers.length})</a></nav>
          <section className="panel" id="solicitar">
            <div className="panel-heading"><div><div className="eyebrow">01 / SOLICITAR UN EJEMPLAR</div><h2>Solicitar un traslado</h2></div><span className="step-ornament">↗</span></div>
            <p className="panel-lede">Elegí el libro y la sucursal que lo recibirá. El origen es <strong>{branchName(branch)}</strong>.</p>
            <form action={requestGuestTransfer} className="field-stack">
              <input type="hidden" name="branch" value={branch} />
              <div className="guest-origin"><span>Origen</span><strong>{branchName(branch)}</strong><span aria-hidden="true">→</span></div>
              <label htmlFor="transfer-destination">Sucursal de destino</label>
              <select id="transfer-destination" name="destination" required disabled={!destinations.length}>
                {destinations.map((b) => <option key={b.branch_id} value={b.branch_id}>{branchName(b.branch_id)}</option>)}
              </select>
              <label htmlFor="transfer-member">Socio que solicita el libro</label>
              <select id="transfer-member" name="member" required>{members.filter((m) => m.enabled).map((m) => <option key={m.id} value={m.id}>{memberLabel(m.code)}</option>)}</select>
              <label htmlFor="transfer-copy">Ejemplar disponible en {branchName(branch)}</label>
              <select id="transfer-copy" name="copy" required disabled={!ownAvailable.length}>
                {ownAvailable.map((c) => <option key={c.id} value={c.id}>{c.title} · {copyLabel(c.code)}</option>)}
              </select>
              <p className="field-hint">Al confirmar, se reserva el ejemplar y comienza el seguimiento del envío.</p>
              <PendingButton className="button button-primary" disabled={!destinations.length || !ownAvailable.length || !members.some((m) => m.enabled)}>
                Solicitar traslado <span aria-hidden="true">↗</span>
              </PendingButton>
            </form>
            {!ownAvailable.length && <p className="field-warning">No hay ejemplares disponibles para enviar desde esta sede. Podés elegir la otra sucursal.</p>}
          </section>
          <section className="panel" id="seguimiento" style={{marginTop:24}}>
            <div className="panel-heading">
              <div><div className="eyebrow">02 / SEGUIMIENTO</div><h2>Préstamos entre sedes</h2></div>
              <span className="record-count">{allTransfers.length} operaciones</span>
            </div>
            <p className="panel-lede">Cada envío avanza paso a paso. Cuando el libro llega, activá el préstamo; al devolverlo, completá el regreso.</p>
            {target && <Link href={`/demo/${branch}/transfers`} className="link-muted">← Ver todos los movimientos</Link>}
            {shown.length === 0 && <p className="empty-state">{target ? "La operación seleccionada no existe en tu espacio." : "Todavía no hay movimientos. Generá una solicitud arriba para comenzar."}</p>}
            {shown.map((loan) => {
              const outbound = loan.transfers.find((t) => t.direction === "OUTBOUND");
              const returnTransfer = loan.transfers.find((t) => t.direction === "RETURN");
              const transfers = [outbound, returnTransfer].filter((t): t is Transfer => Boolean(t));
              const canActivate = loan.status === "REQUESTED" && outbound?.status === "RECEIVED";
              return (
                <article className="transfer-item" key={loan.id}>
                  <div className="panel-heading">
                    <div><div className="eyebrow">PRÉSTAMO #{loan.id}</div><h2>{branchName(loan.origin_branch_id)} → {branchName(loan.destination_branch_id)}</h2></div>
                    <span className="pill pill-muted">{statusName[loan.status] ?? loan.status}</span>
                  </div>
                  <p className="field-hint">{copies.items.find(c => c.id === loan.copy_id)?.title ?? `Ejemplar #${loan.copy_id}`} · {memberName(loan.member_id)}</p>
                  {transfers.map((tr) => {
                    const next = step[tr.status];
                    return (
                      <div key={tr.id} className="transfer-stage">
                        <div className="inventory-row">
                          <span>{tr.direction === "OUTBOUND" ? "Envío" : "Regreso"} #{tr.id} · {branchName(tr.origin_branch_id)} → {branchName(tr.destination_branch_id)}</span>
                          <strong>{statusName[tr.status] ?? tr.status}</strong>
                        </div>
                        <ol className="guest-progress" aria-label="Etapas del traslado">{stages.map((stageName, i) => <li key={stageName} className={i < stages.indexOf(tr.status) ? "done" : i === stages.indexOf(tr.status) ? "current" : ""} aria-current={stageName === tr.status ? "step" : undefined}><span aria-hidden="true">{i < stages.indexOf(tr.status) ? "✓" : i + 1}</span>{statusName[stageName]}</li>)}</ol>
                        {next && <form action={advanceGuestTransfer}>
                          <input type="hidden" name="branch" value={branch} />
                          <input type="hidden" name="transfer" value={tr.id} />
                          <input type="hidden" name="loan" value={loan.id} />
                          <input type="hidden" name="next" value={next.next} />
                          <PendingButton className="button button-primary">{next.label} ↗</PendingButton>
                        </form>}
                      </div>
                    );
                  })}
                  {canActivate && <form action={activateGuestLoan}>
                    <input type="hidden" name="branch" value={branch} />
                    <input type="hidden" name="loan" value={loan.id} />
                    <PendingButton className="button button-primary">Activar préstamo recibido ↗</PendingButton>
                  </form>}
                  {loan.status === "ACTIVE" && <form className="field-stack field-separated" action={returnGuestInterlibraryLoan}>
                    <input type="hidden" name="branch" value={branch} />
                    <input type="hidden" name="loan" value={loan.id} />
                    <label htmlFor={`condition-${loan.id}`}>Estado del ejemplar al devolver</label>
                    <select id={`condition-${loan.id}`} name="condition">
                      <option value="GOOD">Buen estado</option><option value="DAMAGED">Dañado · se retira del catálogo al completar el regreso</option>
                    </select>
                    <PendingButton className="button button-primary">Registrar devolución ↙</PendingButton>
                  </form>}
                  {loan.status === "CLOSED" && <div className="notice"><strong>Operación completada</strong><span>El ejemplar regresó a su origen y el préstamo se cerró en PostgreSQL.</span></div>}
                </article>
              );
            })}
          </section>
          <p className="small-note">Los movimientos se guardan en tu biblioteca temporal. No afectan a otros visitantes.</p>
        </div>
      </main>
    </div>
  );
}
