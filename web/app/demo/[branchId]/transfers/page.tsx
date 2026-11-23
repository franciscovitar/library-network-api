import Link from "next/link";
import { notFound } from "next/navigation";
import { guestApi } from "@/lib/guest-api";
import { positiveId } from "@/lib/input";
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

  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <Link href="/" className="sidebar-brand"><span className="brand-mark">ln<span>·</span></span> Library Network</Link>
        <div className="sidebar-label">TU BIBLIOTECA DE PRUEBA</div>
        <nav className="sidebar-nav" aria-label="Navegación">
          <Link className="nav-link" href={`/demo/${branch}`}>◫ Resumen y préstamos</Link>
          <Link className="nav-link" href={`/demo/${branch}/transfers`}>⇄ Red y traslados</Link>
          {profile.branches.map((b) => <Link className="nav-link" key={b.branch_id} href={`/demo/${b.branch_id}`}>▤ {branchName(b.branch_id)}</Link>)}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-note"><strong>Operaciones auténticas</strong><span>Traslados y eventos guardados en PostgreSQL</span></div>
        </div>
      </aside>
      <main className="workspace-main">
        <header className="workspace-header">
          <div className="breadcrumb"><span>Biblioteca temporal</span><span>/</span><strong>{branchName(branch)}</strong></div>
          <span className="role-badge">Sin registro · Datos aislados</span>
        </header>
        <div className="workspace-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">CIRCULACIÓN ENTRE SEDES / OPERACIONES REALES</div>
              <h1>Un libro,<br/><em>dos sucursales.</em></h1>
              <p>Solicitá un ejemplar de una sede a otra, seguí su traslado, activá el préstamo y completá su devolución. Cada transición se valida en el servidor y conserva su historial.</p>
            </div>
            <Link href={`/demo/${branch}`} className="button button-outline">Volver al resumen ↗</Link>
          </div>
          {notice && <div className={["requested","advanced","activated","returned"].includes(qs.notice ?? "") ? "feedback success" : "feedback error"} role="status">{notice}</div>}
          <section className="panel">
            <div className="panel-heading"><div><div className="eyebrow">01 / SOLICITAR UN EJEMPLAR</div><h2>Transferencia entre sucursales</h2></div><span className="step-ornament">↗</span></div>
            <p className="panel-lede">En esta operación, <strong>{branchName(branch)}</strong> presta uno de sus ejemplares a la sede seleccionada. La solicitud genera un préstamo y un remito real.</p>
            <form action={requestGuestTransfer} className="field-stack">
              <input type="hidden" name="branch" value={branch} />
              <label htmlFor="transfer-destination">Sucursales de destino</label>
              <select id="transfer-destination" name="destination" required disabled={!destinations.length}>
                {destinations.map((b) => <option key={b.branch_id} value={b.branch_id}>{branchName(b.branch_id)}</option>)}
              </select>
              <label htmlFor="transfer-member">Socio que solicita el libro</label>
              <select id="transfer-member" name="member" required>{members.filter((m) => m.enabled).map((m) => <option key={m.id} value={m.id}>{m.code}</option>)}</select>
              <label htmlFor="transfer-copy">Ejemplar disponible en {branchName(branch)}</label>
              <select id="transfer-copy" name="copy" required disabled={!ownAvailable.length}>
                {ownAvailable.map((c) => <option key={c.id} value={c.id}>{c.title} · {c.code.slice(-5)}</option>)}
              </select>
              <p className="field-hint">El sistema comprueba permisos, ubicación y disponibilidad dentro de una única transacción PostgreSQL.</p>
              <button className="button button-primary" type="submit" disabled={!destinations.length || !ownAvailable.length || !members.some((m) => m.enabled)}>
                Solicitar traslado <span aria-hidden="true">↗</span>
              </button>
            </form>
            {!ownAvailable.length && <p className="field-warning">No hay ejemplares disponibles para enviar desde esta sede. Podés elegir la otra sucursal.</p>}
          </section>
          <section className="panel" style={{marginTop:24}}>
            <div className="panel-heading">
              <div><div className="eyebrow">02 / SEGUIMIENTO</div><h2>Préstamos entre sedes</h2></div>
              <span className="record-count">{allTransfers.length} operaciones</span>
            </div>
            <p className="panel-lede">Las etapas son secuenciales: preparado → despachado → en tránsito → recibido. Una vez recibido, podés activar el préstamo y luego completar la devolución a la sede de origen.</p>
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
                  <p className="field-hint">Ejemplar #{loan.copy_id} · Socio {members.find((m) => m.id === loan.member_id)?.code ?? "registrado"}</p>
                  {transfers.map((tr) => {
                    const next = step[tr.status];
                    return (
                      <div key={tr.id} className="transfer-stage">
                        <div className="inventory-row">
                          <span>{tr.direction === "OUTBOUND" ? "Envío" : "Regreso"} #{tr.id} · {branchName(tr.origin_branch_id)} → {branchName(tr.destination_branch_id)}</span>
                          <strong>{statusName[tr.status] ?? tr.status}</strong>
                        </div>
                        {next && <form action={advanceGuestTransfer}>
                          <input type="hidden" name="branch" value={branch} />
                          <input type="hidden" name="transfer" value={tr.id} />
                          <input type="hidden" name="loan" value={loan.id} />
                          <input type="hidden" name="next" value={next.next} />
                          <button type="submit" className="button button-outline">{next.label} ↗</button>
                        </form>}
                      </div>
                    );
                  })}
                  {canActivate && <form action={activateGuestLoan}>
                    <input type="hidden" name="branch" value={branch} />
                    <input type="hidden" name="loan" value={loan.id} />
                    <button className="button button-primary" type="submit">Activar préstamo recibido ↗</button>
                  </form>}
                  {loan.status === "ACTIVE" && <form className="field-stack field-separated" action={returnGuestInterlibraryLoan}>
                    <input type="hidden" name="branch" value={branch} />
                    <input type="hidden" name="loan" value={loan.id} />
                    <label htmlFor={`condition-${loan.id}`}>Estado del ejemplar al devolver</label>
                    <select id={`condition-${loan.id}`} name="condition">
                      <option value="GOOD">Buen estado</option><option value="DAMAGED">Dañado · se retira del catálogo al completar el regreso</option>
                    </select>
                    <button className="button button-primary" type="submit">Registrar devolución ↙</button>
                  </form>}
                  {loan.status === "CLOSED" && <div className="notice"><strong>Operación completada</strong><span>El ejemplar regresó a su origen y el préstamo se cerró en PostgreSQL.</span></div>}
                </article>
              );
            })}
          </section>
          <p className="small-note">Espacio sintético individual con operaciones persistentes. El historial de movimientos no se inventa en el navegador.</p>
        </div>
      </main>
    </div>
  );
}
