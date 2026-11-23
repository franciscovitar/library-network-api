import Link from "next/link";
import { notFound } from "next/navigation";
import { issueLoan, returnLoan } from "../actions";
import { staffApi, StaffApiError } from "@/lib/api";
import { boundedSearch, positiveId } from "@/lib/input";
import { feedback } from "@/lib/navigation";
import type { BranchCopy, CopyPage, Loan, MemberLookup, StaffProfile } from "@/lib/types";

export const metadata = { title: "Circulación" };
export const dynamic = "force-dynamic";

const canOperate = (role: string) => role !== "VIEWER";

export default async function Circulation({
  params, searchParams,
}: {
  params: Promise<{ branchId: string }>;
  searchParams: Promise<{ member?: string; copies?: string; copy?: string; loan?: string; notice?: string }>;
}) {
  const branchId = positiveId((await params).branchId);
  if (!branchId) notFound();
  const p = await searchParams;
  const memberCode = boundedSearch(p.member, 32).toUpperCase();
  const copiesQuery = boundedSearch(p.copies, 100);
  const pickedCopy = positiveId(p.copy);
  const requestedLoanId = positiveId(p.loan);
  const [profile, copyPage] = await Promise.all([
    staffApi<StaffProfile>("/api/v2/me"),
    staffApi<CopyPage>(`/api/v2/branches/${branchId}/copies?${new URLSearchParams({ limit: "30", ...(copiesQuery ? { q: copiesQuery } : {}) })}`),
  ]);
  const grant = profile.branches.find((b) => b.branch_id === branchId);
  if (!grant) notFound();
  const writeAccess = canOperate(grant.role);
  let member: MemberLookup | null = null;
  let memberMissing = false;
  if (memberCode) {
    try {
      member = await staffApi<MemberLookup>(`/api/v2/branches/${branchId}/members/lookup?code=${encodeURIComponent(memberCode)}`);
    } catch (error) {
      if (error instanceof StaffApiError && error.status === 404) memberMissing = true;
      else throw error;
    }
  }
  let loan: Loan | null = null;
  let loanMissing = false;
  if (requestedLoanId) {
    try {
      loan = await staffApi<Loan>(`/api/v2/loans/${requestedLoanId}`);
    } catch (error) {
      if (error instanceof StaffApiError && error.status === 404) loanMissing = true;
      else throw error;
    }
  }
  const notice = feedback(p.notice);
  const available = copyPage.items.filter((copy) => copy.status === "AVAILABLE");
  const base = `/workspace/${branchId}/circulation`;
  const selected = available.some((copy) => copy.id === pickedCopy) ? pickedCopy : available[0]?.id;
  return <main>
    <div className="page-heading">
      <div><div className="eyebrow">CIRCULACIÓN · OPERACIONES REALES</div><h1>Préstamos y <em>devoluciones.</em></h1>
        <p>Todos los movimientos se validan y registran en el servidor. No hay operaciones simuladas en el navegador.</p></div>
      <Link href={`/workspace/${branchId}/catalog`} className="button button-outline">Ver catálogo ↗</Link>
    </div>
    {notice && <div role="status" className={notice.tone === "success" ? "feedback success" : "feedback error"}>{notice.text}</div>}
    {!writeAccess && <div className="notice"><strong>Solo consulta</strong><span>Tu rol permite visualizar datos, pero no registrar préstamos ni devoluciones.</span></div>}
    <div className="circulation-grid">
      <section className="panel">
        <div className="panel-heading"><div><div className="eyebrow">01 / SALIDA</div><h2>Registrar préstamo local</h2></div><span className="step-ornament">↗</span></div>
        <p className="panel-lede">Primero identificá al socio y después seleccioná un ejemplar disponible de esta sucursal.</p>
        <form action={base} method="GET" className="field-stack">
          <label htmlFor="member-code">Código de socio</label>
          <div className="inline-fields"><input id="member-code" name="member" defaultValue={memberCode} placeholder="Ej.: M0001" maxLength={32} autoComplete="off" required /><button className="button button-outline" type="submit">Buscar socio</button></div>
          {pickedCopy && <input type="hidden" name="copy" value={pickedCopy} />}
          {copiesQuery && <input type="hidden" name="copies" value={copiesQuery} />}
        </form>
        {memberMissing && <p className="field-warning">No encontramos un socio con ese código.</p>}
        {member && <div className={member.enabled ? "member-found" : "member-found member-disabled"}>
          <span>{member.enabled ? "Socio habilitado" : "Socio deshabilitado"}</span><strong>{member.code}</strong>
          <span className="subtle-text">Identificador interno: #{member.id}</span></div>}
        <form action={base} method="GET" className="field-stack field-separated">
          <label htmlFor="copies-query">Buscar ejemplar por código, título o autor</label>
          <div className="inline-fields"><input id="copies-query" name="copies" defaultValue={copiesQuery} placeholder="Ej.: CP-0001 o Synthetic" maxLength={100} /><button type="submit" className="button button-outline">Buscar</button></div>
          {memberCode && <input type="hidden" name="member" value={memberCode} />}
        </form>
        <form action={issueLoan} className="field-stack field-separated">
          <input type="hidden" name="branchId" value={branchId} />
          <input type="hidden" name="memberId" value={member?.id ?? ""} />
          <label htmlFor="copy-id">Ejemplar disponible</label>
          <select id="copy-id" name="copyId" defaultValue={selected ? String(selected) : ""} disabled={!writeAccess || !member?.enabled || available.length === 0} required>
            {available.length === 0 && <option value="">No hay ejemplares disponibles</option>}
            {available.map((copy: BranchCopy) => <option key={copy.id} value={copy.id}>{copy.code} · {copy.title}</option>)}
          </select>
          <p className="field-hint">{available.length} ejemplares disponibles en esta búsqueda. El servidor vuelve a comprobar disponibilidad al confirmar.</p>
          <button type="submit" className="button button-primary full-width" disabled={!writeAccess || !member?.enabled || available.length === 0}>Confirmar préstamo <span aria-hidden="true">↗</span></button>
        </form>
      </section>
      <section className="panel">
        <div className="panel-heading"><div><div className="eyebrow">02 / DEVOLUCIÓN</div><h2>Registrar una devolución</h2></div><span className="step-ornament">↙</span></div>
        <p className="panel-lede">Consultá el número de préstamo para comprobar su estado y la sucursal antes de registrar la recepción.</p>
        <form action={base} method="GET" className="field-stack">
          <label htmlFor="lookup-loan">Número de préstamo</label>
          <div className="inline-fields"><input id="lookup-loan" name="loan" type="number" min={1} step={1} defaultValue={requestedLoanId ?? ""} placeholder="Ej.: 42" required /><button className="button button-outline" type="submit">Consultar</button></div>
        </form>
        {loanMissing && <p className="field-warning">No encontramos ese préstamo en tu ámbito autorizado.</p>}
        {loan && <div className="loan-preview"><div className="inventory-row"><span>Préstamo</span><strong>#{loan.id}</strong></div>
          <div className="inventory-row"><span>Tipo</span><strong>{loan.kind === "LOCAL" ? "Local" : "Entre sucursales"}</strong></div>
          <div className="inventory-row"><span>Estado</span><strong>{loan.status}</strong></div>
          <div className="inventory-row"><span>Ejemplar</span><strong>#{loan.copy_id}</strong></div>
          {loan.due_at && <div className="inventory-row"><span>Vencimiento</span><strong>{new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeZone: "UTC" }).format(new Date(loan.due_at))}</strong></div>}
        </div>}
        {loan?.kind === "INTERLIBRARY" && <p className="field-warning">Este préstamo exige el circuito de devolución interbibliotecaria; no se puede cerrar como local.</p>}
        {loan?.status === "CLOSED" && <p className="small-note">Este préstamo ya está cerrado.</p>}
        {loan?.kind === "LOCAL" && loan.status === "ACTIVE" && <form action={returnLoan} className="field-stack field-separated">
          <input type="hidden" name="branchId" value={branchId} /><input type="hidden" name="loanId" value={loan.id} />
          <label htmlFor="return-condition">Estado físico al recibir</label>
          <select name="condition" id="return-condition"><option value="GOOD">Buen estado · vuelve al catálogo</option><option value="DAMAGED">Dañado · retirar de circulación</option></select>
          <p className="field-hint">Si marcás «dañado», el ejemplar no volverá a estar disponible.</p>
          <button type="submit" className="button button-primary full-width" disabled={!writeAccess}>Confirmar devolución <span aria-hidden="true">↙</span></button>
        </form>}
        {!loan && !loanMissing && <div className="empty-prompt">Ingresá un número de préstamo para ver su detalle antes de operar.</div>}
      </section>
    </div>
    <div className="notice"><strong>Registro transaccional</strong><span>Un préstamo local bloquea el ejemplar real y conserva su fecha de vencimiento. La devolución actualiza el mismo registro; no modificamos disponibilidad en el navegador.</span></div>
  </main>;
}
