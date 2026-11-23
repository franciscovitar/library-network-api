import Link from "next/link";
import { notFound } from "next/navigation";
import { staffApi } from "@/lib/api";
import { boundedSearch, positiveId } from "@/lib/input";
import type { BranchCopy, CatalogPage, CopyPage } from "@/lib/types";

export const metadata = { title: "Catálogo" };
export const dynamic = "force-dynamic";

function statusLabel(copy: BranchCopy): string {
  const names: Record<string, string> = {
    AVAILABLE: "Disponible",
    ON_LOAN: "En préstamo",
    RESERVED: "Reservado",
    IN_TRANSIT: "En tránsito",
    RETIRED: "Retirado",
  };
  return names[copy.status] ?? copy.status;
}

export default async function Catalog({
  params,
  searchParams,
}: {
  params: Promise<{ branchId: string }>;
  searchParams: Promise<{ q?: string; page?: string }>;
}) {
  const branchId = positiveId((await params).branchId);
  if (!branchId) notFound();
  const p = await searchParams;
  const q = boundedSearch(p.q);
  const page = positiveId(p.page ?? "1") ?? 1;
  const offset = Math.min((page - 1) * 20, 100000);
  const qs = new URLSearchParams({ branch_id: String(branchId), limit: "20", offset: String(offset) });
  if (q) qs.set("q", q);
  const copyQs = new URLSearchParams({ limit: "20" });
  if (q) copyQs.set("q", q);
  const [catalog, copies] = await Promise.all([
    staffApi<CatalogPage>(`/api/v2/catalog/search?${qs.toString()}`),
    staffApi<CopyPage>(`/api/v2/branches/${branchId}/copies?${copyQs.toString()}`),
  ]);
  const base = `/workspace/${branchId}/catalog`;
  const previous = new URLSearchParams({ q, page: String(page - 1) });
  const following = new URLSearchParams({ q, page: String(page + 1) });
  return (
    <main>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CATÁLOGO · REGISTROS DEL SERVIDOR</div>
          <h1>Libros y <em>ejemplares.</em></h1>
          <p>Encontrá títulos y su disponibilidad real en la sucursal. Cada ejemplar conserva identidad y estado propios.</p>
        </div>
        <Link href={`/workspace/${branchId}/circulation`} className="button button-primary">Ir a circulación <span aria-hidden="true">↗</span></Link>
      </div>
      <form className="search-panel" action={base} method="GET" role="search">
        <label htmlFor="catalog-query">Buscar por título, autor, ISBN o código de ejemplar</label>
        <div className="search-controls"><input id="catalog-query" name="q" defaultValue={q} placeholder="Ej.: Synthetic Tales o CP-0001" maxLength={100} />
          <button type="submit" className="button button-primary">Buscar</button>
          {q && <Link href={base} className="button button-outline">Limpiar</Link>}
        </div>
      </form>
      <div className="panel table-panel">
        <div className="panel-heading"><div><div className="eyebrow">TÍTULOS</div><h2>Catálogo de la red</h2></div><span className="record-count">{catalog.total} resultados</span></div>
        {catalog.items.length === 0 ? <p className="empty-state">No hay títulos para esta búsqueda.</p> : (
          <div className="table-scroll"><table>
            <thead><tr><th>Título</th><th>ISBN</th><th>Ejemplares en sede</th><th>Disponibles</th></tr></thead>
            <tbody>{catalog.items.map((book) => <tr key={book.id}>
              <td><strong>{book.title}</strong><span className="subtle-text">{book.author}</span></td>
              <td className="mono">{book.isbn}</td><td>{book.total_copies}</td>
              <td><span className={book.available_copies > 0 ? "pill pill-available" : "pill pill-muted"}>{book.available_copies} disponibles</span></td>
            </tr>)}</tbody>
          </table></div>
        )}
        <div className="table-footer"><span>Mostrando {catalog.items.length} de {catalog.total}</span><div className="pagination">
          {page > 1 && <Link href={`${base}?${previous.toString()}`}>← Anterior</Link>}
          {offset + catalog.items.length < catalog.total && <Link href={`${base}?${following.toString()}`}>Siguiente →</Link>}
        </div></div>
      </div>
      <section className="panel table-panel">
        <div className="panel-heading"><div><div className="eyebrow">INVENTARIO LOCAL</div><h2>Ejemplares identificables</h2></div><span className="record-count">{copies.total} en esta búsqueda</span></div>
        {copies.items.length === 0 ? <p className="empty-state">No se encontraron ejemplares propios de esta sucursal.</p> : (
          <div className="table-scroll"><table>
            <thead><tr><th>Código</th><th>Libro</th><th>Estado</th><th>Acción</th></tr></thead>
            <tbody>{copies.items.map((copy) => <tr key={copy.id}>
              <td className="mono">{copy.code}</td><td><strong>{copy.title}</strong><span className="subtle-text">{copy.author}</span></td>
              <td><span className={copy.status === "AVAILABLE" ? "pill pill-available" : "pill pill-muted"}>{statusLabel(copy)}</span></td>
              <td>{copy.status === "AVAILABLE" ? <Link href={`/workspace/${branchId}/circulation?copy=${copy.id}`}>Prestar ↗</Link> : <span className="subtle-text">No disponible</span>}</td>
            </tr>)}</tbody>
          </table></div>
        )}
      </section>
    </main>
  );
}
