import Link from "next/link";
import { notFound } from "next/navigation";
import { guestApi } from "@/lib/guest-api";
import { boundedSearch, positiveId } from "@/lib/input";
import type { Overview, Loan } from "@/lib/types";
import type { GuestProfile, GuestCatalog, GuestCopyPage, GuestMember } from "@/lib/guest-types";
import { guestIssue, guestReturn } from "./actions";
import { restartDemo } from "@/app/demo/actions";

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
  const [profile, overview, catalog, copies, members] = await Promise.all([
    guestApi<GuestProfile>("/api/v2/guest/me"),
    guestApi<Overview>(`/api/v2/guest/branches/${branch}/overview`),
    guestApi<GuestCatalog>(`/api/v2/guest/branches/${branch}/catalog${query}`),
    guestApi<GuestCopyPage>(`/api/v2/guest/branches/${branch}/copies${query}`),
    guestApi<GuestMember[]>("/api/v2/guest/members"),
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
    issued: "Préstamo registrado en PostgreSQL.",
    returned: "Devolución registrada. El ejemplar vuelve a estar disponible.",
    invalid: "Seleccioná un socio y un ejemplar válidos.",
    denied: "No tenés acceso a ese recurso.",
    conflict: "El estado del libro cambió. Volvé a consultar la disponibilidad.",
    quota: "Alcanzaste el límite de operaciones de este espacio temporal.",
    unavailable: "La operación no pudo confirmarse. Probá nuevamente.",
  };
  const feedback = p.notice ? messages[p.notice] : undefined;
  const available = copies.items.filter(copy => copy.status === "AVAILABLE");
  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <Link href="/" className="sidebar-brand"><span className="brand-mark">ln<span>·</span></span> Library Network</Link>
        <div className="sidebar-label">EXPLORACIÓN SIN REGISTRO</div>
        <nav className="sidebar-nav" aria-label="Sucursales del espacio de prueba">
          <Link className="nav-link" href={`/demo/${branch}/transfers`}>⇄ Red y traslados</Link>
          {profile.branches.map(b => <Link className="nav-link" key={b.branch_id} href={`/demo/${b.branch_id}`}>◫ {b.name.split("· ").at(-1)}</Link>)}
        </nav>
        <div className="sidebar-bottom"><div className="workspace-note"><strong>Aplicación real</strong><span>Datos ficticios, operaciones persistentes</span></div></div>
      </aside>
      <main className="workspace-main">
        <header className="workspace-header"><div className="breadcrumb"><span>Library Network</span><span>/</span><strong>{current.name.split("· ").at(-1)}</strong></div><span className="role-badge">Acceso público · sin login</span></header>
        <div className="workspace-content">
          <div className="page-heading">
            <div><div className="eyebrow">BIBLIOTECA DE PRUEBA · ENTORNO AISLADO</div><h1>Una biblioteca<br /><em>en movimiento.</em></h1>
              <p>Usá este sistema como un bibliotecario: buscá un libro, prestalo y devolvelo. Los cambios se guardan realmente en PostgreSQL y son exclusivos de tu visita.</p></div>
            <div className="page-action-group">
              <Link className="button button-primary" href={`/demo/${branch}/transfers`}>Operaciones entre sedes ↗</Link>
              <Link className="button button-outline" href="/">Acerca del producto ↗</Link>
              <form action={restartDemo}><button type="submit" className="button button-outline">Crear otra biblioteca temporal</button></form>
            </div>
          </div>
          {feedback && <div role="status" className="feedback success">{feedback}</div>}
          <section className="stat-grid" aria-label="Estado actual de esta sucursal">
            {[["Préstamos activos",overview.active_loans],["Ejemplares disponibles",overview.available_copies],["Títulos catalogados",overview.catalog_titles],["Traslados pendientes",overview.pending_arrivals]].map(([label,value]) => (
              <div className="stat-card" key={String(label)}><span className="stat-label">{label}</span><strong className="stat-value">{value}</strong><span className="stat-caption">Consultado en PostgreSQL</span></div>
            ))}
          </section>
          <form className="search-panel" action={`/demo/${branch}`} method="GET">
            <label htmlFor="guest-search">Explorar catálogo · título, autor o ejemplar</label>
            <div className="search-controls"><input id="guest-search" name="q" placeholder="Ej.: atlas" defaultValue={q} maxLength={100}/><button className="button button-primary" type="submit">Buscar</button></div>
          </form>
          <section className="panel table-panel"><div className="panel-heading"><div><div className="eyebrow">CATÁLOGO OPERATIVO</div><h2>Libros de esta sucursal</h2></div><span className="record-count">{catalog.total} títulos</span></div>
            <div className="table-scroll"><table><thead><tr><th>Título</th><th>Autor</th><th>Ejemplares</th><th>Disponibles</th></tr></thead><tbody>
              {catalog.items.map(book => <tr key={book.id}><td><strong>{book.title}</strong></td><td>{book.author}</td><td>{book.total_copies}</td><td><span className={book.available_copies ? "pill pill-available" : "pill pill-muted"}>{book.available_copies}</span></td></tr>)}
            </tbody></table></div>
          </section>
          <div className="circulation-grid">
            <section className="panel"><div className="panel-heading"><div><div className="eyebrow">OPERACIÓN REAL / 01</div><h2>Registrar préstamo</h2></div></div>
              <p className="panel-lede">Elegí un socio ficticio y un ejemplar disponible. La aplicación verificará el stock y registrará el préstamo de manera transaccional.</p>
              <form action={guestIssue} className="field-stack">
                <input type="hidden" name="branch" value={branch}/>
                <label htmlFor="guest-member">Socio</label><select id="guest-member" name="member" required>{members.map(m => <option key={m.id} value={m.id}>{m.code}</option>)}</select>
                <label htmlFor="guest-copy">Ejemplar disponible</label><select id="guest-copy" name="copy" required disabled={!available.length}>{available.map(c => <option key={c.id} value={c.id}>{c.title} · {c.code.slice(-5)}</option>)}</select>
                <p className="field-hint">La disponibilidad vuelve a validarse en el servidor al confirmar.</p>
                <button className="button button-primary full-width" type="submit" disabled={!available.length}>Registrar préstamo ↗</button>
              </form>
            </section>
            <section className="panel"><div className="panel-heading"><div><div className="eyebrow">OPERACIÓN REAL / 02</div><h2>Devolver un ejemplar</h2></div></div>
              <p className="panel-lede">Ingresá el número de préstamo para comprobar su estado antes de devolverlo.</p>
              <form action={`/demo/${branch}`} method="GET" className="field-stack">
                <label htmlFor="guest-loan">Identificador de préstamo</label><div className="inline-fields"><input id="guest-loan" name="loan" type="number" min="1" defaultValue={selectedLoan ?? ""} placeholder="Ej.: 21"/><button type="submit" className="button button-outline">Consultar</button></div>
              </form>
              {loan && <div className="loan-preview"><div className="inventory-row"><span>Préstamo #{loan.id}</span><strong>{loan.status}</strong></div><div className="inventory-row"><span>Tipo</span><strong>{loan.kind}</strong></div></div>}
              {loan?.status === "ACTIVE" && loan.kind === "LOCAL" && <form action={guestReturn} className="field-stack field-separated"><input type="hidden" name="branch" value={branch}/><input type="hidden" name="loan" value={loan.id}/><button className="button button-primary full-width" type="submit">Confirmar devolución ↙</button></form>}
              {!loan && <p className="empty-prompt">Podés consultar el préstamo creado en el paso anterior.</p>}
            </section>
          </div>
          <div className="notice"><strong>Tu espacio es temporal</strong><span>Los datos son sintéticos y tu acceso vence en 24 horas. Crear otra biblioteca abre un espacio distinto, sin borrar ni invalidar el anterior. La limpieza transaccional de espacios vencidos existe, pero su programación automática sigue pendiente.</span></div>
        </div>
      </main>
    </div>
  );
}
