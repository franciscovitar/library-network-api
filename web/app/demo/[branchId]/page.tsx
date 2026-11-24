import Link from "next/link";
import { notFound } from "next/navigation";
import { guestApi } from "@/lib/guest-api";
import { boundedSearch, positiveId } from "@/lib/input";
import type { Overview, Loan } from "@/lib/types";
import type { GuestProfile, GuestCatalog, GuestCopyPage, GuestMember } from "@/lib/guest-types";
import { guestIssue, guestReturn } from "./actions";
import { restartDemo } from "@/app/demo/actions";
import GuestNav from "@/components/GuestNav";
import PendingButton from "@/components/PendingButton";
import { memberLabel, copyLabel, shortBranch, loanStatus, dateLabel } from "@/lib/guest-display";

export const dynamic = "force-dynamic";
export const metadata = { title: "Explorar biblioteca" };

export default async function GuestDashboard({
  params, searchParams,
}: {
  params: Promise<{ branchId: string }>;
  searchParams: Promise<{ q?: string; loan?: string; notice?: string }>;
}) {
  const branch = positiveId((await params).branchId);
  if (!branch) notFound();
  const p = await searchParams;
  const q = boundedSearch(p.q);
  const query = q ? `?q=${encodeURIComponent(q)}` : "";
  const [profile, overview, catalog, copies, members, loans, allCopies] = await Promise.all([
    guestApi<GuestProfile>("/api/v2/guest/me"),
    guestApi<Overview>(`/api/v2/guest/branches/${branch}/overview`),
    guestApi<GuestCatalog>(`/api/v2/guest/branches/${branch}/catalog${query}`),
    guestApi<GuestCopyPage>(`/api/v2/guest/branches/${branch}/copies${query}`),
    guestApi<GuestMember[]>("/api/v2/guest/members"),
    guestApi<Loan[]>("/api/v2/guest/loans?limit=50"),
    q ? guestApi<GuestCopyPage>(`/api/v2/guest/branches/${branch}/copies`) : Promise.resolve(null),
  ]);
  const current = profile.branches.find(b => b.branch_id === branch);
  if (!current) notFound();
  const selectedLoan = positiveId(p.loan);
  let loan: Loan | null = null;
  if (selectedLoan) {
    try { loan = await guestApi<Loan>(`/api/v2/guest/loans/${selectedLoan}`); }
    catch { loan = null; }
  }
  const messages: Record<string, string> = {
    issued: "¡Préstamo registrado! Podés devolverlo desde la lista de préstamos activos.",
    returned: "Devolución registrada. El ejemplar vuelve a estar disponible.",
    invalid: "Seleccioná un socio y un ejemplar válidos.",
    denied: "No tenés acceso a ese recurso.",
    conflict: "El estado del libro cambió. Volvé a consultar la disponibilidad.",
    quota: "Alcanzaste el límite de operaciones de este espacio temporal.",
    unavailable: "La operación no pudo confirmarse. Probá nuevamente.",
  };
  const feedback = p.notice && Object.hasOwn(messages, p.notice) ? messages[p.notice] : undefined;
  const successful = p.notice === "issued" || p.notice === "returned";
  const active = loans.filter(l => l.status === "ACTIVE" && l.kind === "LOCAL" && l.destination_branch_id === branch);
  const enabledMembers = members.filter(m => m.enabled);
  const memberName = (id: number) => { const m = members.find(item => item.id === id); return m ? memberLabel(m.code) : "Socio de prueba"; };
  const bookName = (id: number) => (allCopies ?? copies).items.find(c => c.id === id)?.title ?? `Ejemplar #${id}`;
  const available = copies.items.filter(copy => copy.status === "AVAILABLE");
  return (
    <div className="workspace-shell guest-shell">
      <GuestNav profile={profile} branch={branch}/>
      <main className="workspace-main">
        <header className="workspace-header"><div className="breadcrumb"><span>Library Network</span><span>/</span><strong>{shortBranch(current.name)}</strong></div><span className="role-badge">Acceso público · sin login</span></header>
        <div className="workspace-content">
          <div className="page-heading guest-heading" id="resumen">
            <div><div className="eyebrow">TU BIBLIOTECA · {shortBranch(current.name)}</div><h1>Resumen de biblioteca</h1><p>Buscá libros, registrá préstamos y gestioná devoluciones o traslados. Elegí una tarea para empezar.</p></div>
            <form action={restartDemo}><PendingButton className="button button-outline" pendingLabel="Creando biblioteca…">Crear otra biblioteca temporal</PendingButton></form>
          </div>
          {feedback && <div role="status" className={`feedback ${successful ? "success" : "error"}`}>{feedback}</div>}
          <nav className="guest-quick-actions" aria-label="Accesos rápidos">
            <a href="#catalogo"><span aria-hidden="true">▤</span><strong>Buscar libro</strong><small>Consultar disponibilidad</small></a>
            <a href="#prestamos"><span aria-hidden="true">↗</span><strong>Prestar libro</strong><small>Registrar una salida</small></a>
            <a href="#devoluciones"><span aria-hidden="true">↙</span><strong>Devolver libro</strong><small>Ver préstamos activos</small></a>
            <Link href={`/demo/${branch}/transfers`} aria-label="Operaciones entre sedes"><span aria-hidden="true">⇄</span><strong>Solicitar traslado</strong><small>Enviar a otra sucursal</small></Link>
          </nav>
          <section className="stat-grid" aria-label="Estado actual de esta sucursal">
            {[["Préstamos activos",overview.active_loans],["Ejemplares disponibles",overview.available_copies],["Títulos catalogados",overview.catalog_titles],["Traslados pendientes",overview.pending_arrivals]].map(([label,value]) => (
              <div className="stat-card" key={String(label)}><span className="stat-label">{label}</span><strong className="stat-value">{value}</strong><span className="stat-caption">En esta sucursal</span></div>
            ))}
          </section>
          <form id="catalogo" className="search-panel" action={`/demo/${branch}#catalogo`} method="GET">
            <label htmlFor="guest-search">Buscar en el catálogo</label>
            <div className="search-controls"><input id="guest-search" name="q" placeholder="Título o autor, ej.: atlas" defaultValue={q} maxLength={100}/><button className="button button-primary" type="submit">Buscar</button>{q && <a href={`/demo/${branch}#catalogo`} className="button button-outline">Limpiar</a>}</div>
          </form>
          <section className="panel table-panel"><div className="panel-heading"><div><div className="eyebrow">CATÁLOGO OPERATIVO</div><h2>Libros de esta sucursal</h2></div><span className="record-count">{catalog.total} títulos</span></div>
            <div className="table-scroll"><table><thead><tr><th>Título</th><th>Autor</th><th>Ejemplares</th><th>Disponibles</th></tr></thead><tbody>
              {catalog.items.map(book => <tr key={book.id}><td><strong>{book.title}</strong></td><td>{book.author}</td><td>{book.total_copies}</td><td><span className={book.available_copies ? "pill pill-available" : "pill pill-muted"}>{book.available_copies}</span></td></tr>)}
            </tbody></table></div>{catalog.items.length === 0 && <p className="empty-state">No encontramos libros con esa búsqueda. Probá otro título o autor.</p>}
          </section>
          <div className="circulation-grid">
            <section className="panel" id="prestamos"><div className="panel-heading"><div><div className="eyebrow">PRÉSTAMOS</div><h2>Registrar préstamo</h2></div></div>
              <p className="panel-lede">Elegí quién se lleva el libro y qué ejemplar va a retirar. El sistema comprueba automáticamente su disponibilidad.</p>
              <form action={guestIssue} className="field-stack">
                <input type="hidden" name="branch" value={branch}/>
                <label htmlFor="guest-member">Socio</label><select id="guest-member" name="member" required>{enabledMembers.map(m => <option key={m.id} value={m.id}>{memberLabel(m.code)}</option>)}</select>
                <label htmlFor="guest-copy">Ejemplar disponible</label><select id="guest-copy" name="copy" required disabled={!available.length}>{available.map(c => <option key={c.id} value={c.id}>{c.title} · {copyLabel(c.code)}</option>)}</select>
                <p className="field-hint">{available.length ? `${available.length} ejemplares disponibles para prestar.` : "No hay ejemplares disponibles con la búsqueda actual."}</p>
                <PendingButton className="button button-primary full-width" disabled={!available.length || !enabledMembers.length}>Registrar préstamo ↗</PendingButton>
              </form>
            </section>
            <section className="panel" id="devoluciones"><div className="panel-heading"><div><div className="eyebrow">DEVOLUCIONES</div><h2>Devolver un ejemplar</h2></div><span className="record-count">{active.length} activos</span></div>
              <p className="panel-lede">Elegí el préstamo que querés cerrar. El libro volverá a estar disponible en esta sucursal.</p>
              {active.length === 0 && <p className="empty-prompt">No hay préstamos locales activos. Registrá un préstamo para probar una devolución.</p>}
              <div className="guest-loan-list">{active.map(item => <article key={item.id} className="guest-loan">
                <strong>{bookName(item.copy_id)}</strong><span>{memberName(item.member_id)}</span><span className="subtle-text">Préstamo #{item.id} · Vence: {dateLabel(item.due_at)}</span>
                <form action={guestReturn}><input type="hidden" name="branch" value={branch}/><input type="hidden" name="loan" value={item.id}/><PendingButton className="button button-primary full-width">Confirmar devolución ↙</PendingButton></form>
              </article>)}</div>
              <details className="guest-manual" open={selectedLoan !== null && !active.some(item => item.id === selectedLoan)}>
                <summary>Consultar por número de préstamo</summary>
                <form action={`/demo/${branch}#devoluciones`} method="GET" className="field-stack">
                  <label htmlFor="guest-loan">Identificador de préstamo</label><div className="inline-fields"><input id="guest-loan" name="loan" type="number" min="1" defaultValue={selectedLoan ?? ""} placeholder="Ej.: 21"/><button type="submit" className="button button-outline">Consultar</button></div>
                </form>
                {loan && <div className="loan-preview"><div className="inventory-row"><span>Préstamo #{loan.id}</span><strong>{loanStatus(loan.status)}</strong></div><div className="inventory-row"><span>Tipo</span><strong>{loan.kind === "LOCAL" ? "Local" : "Entre sucursales"}</strong></div></div>}
                {loan?.status === "ACTIVE" && loan.kind === "LOCAL" && loan.destination_branch_id !== branch && <Link href={`/demo/${loan.destination_branch_id}#devoluciones`}>Ir a la sucursal del préstamo</Link>}
                {loan?.kind === "INTERLIBRARY" && <Link href={`/demo/${branch}/transfers?loan=${loan.id}`}>Ver seguimiento del traslado</Link>}
                {selectedLoan && !loan && <p className="field-warning">No pudimos consultar ese préstamo. Verificá el número o volvé a intentar.</p>}
              </details>
            </section>
          </div>
          <div className="notice"><strong>Tu espacio es temporal</strong><span>Estás usando datos ficticios, separados de otras visitas. El acceso vence en 24 horas. Crear otra biblioteca abre un espacio nuevo. Los cambios se guardan realmente en PostgreSQL.</span></div>
        </div>
      </main>
    </div>
  );
}
