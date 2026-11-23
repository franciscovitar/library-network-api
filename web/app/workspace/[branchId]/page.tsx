import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { staffApi } from "@/lib/api";
import { positiveId } from "@/lib/input";
import type { Overview } from "@/lib/types";

export const metadata: Metadata = { title: "Resumen operativo" };
export const dynamic = "force-dynamic";

export default async function BranchHome({ params }: { params: Promise<{ branchId: string }> }) {
  const branchId = positiveId((await params).branchId);
  if (!branchId) notFound();
  const summary = await staffApi<Overview>(`/api/v2/branches/${branchId}/overview`);
  const cards = [
    { label: "Préstamos activos", value: summary.active_loans, description: "Ejemplares en circulación", href: "circulation" },
    { label: "Disponibles", value: summary.available_copies, description: `De ${summary.total_copies} ejemplares en sede`, href: "catalog" },
    { label: "Vencidos", value: summary.overdue_loans, description: "Préstamos fuera de término", href: "circulation" },
    { label: "Por recibir", value: summary.pending_arrivals, description: "Traslados en camino", href: "" },
  ];
  return <main>
    <div className="page-heading"><div><div className="eyebrow">CENTRO DE OPERACIONES</div><h1>Tu biblioteca,<br /><em>al día.</em></h1><p>Situación actual de la sucursal. Datos consultados directamente en PostgreSQL.</p></div>
      <Link className="button button-primary" href={`/workspace/${branchId}/circulation`}>Registrar préstamo <span aria-hidden="true">↗</span></Link>
    </div>
    <section className="stat-grid" aria-label="Indicadores de la sucursal">{cards.map((c) => (
      <Link className="stat-card" href={c.href ? `/workspace/${branchId}/${c.href}` : `/workspace/${branchId}`} key={c.label}>
        <span className="stat-label">{c.label}</span><strong className="stat-value">{c.value.toLocaleString("es-AR")}</strong><span className="stat-caption">{c.description}</span>
      </Link>
    ))}</section>
    <div className="dashboard-grid">
      <section className="panel"><div className="panel-heading"><div><div className="eyebrow">RESUMEN DE CATÁLOGO</div><h2>Inventario de la sede</h2></div><Link href={`/workspace/${branchId}/catalog`}>Ver catálogo ↗</Link></div>
        <div className="inventory-row"><span>Títulos únicos</span><strong>{summary.catalog_titles.toLocaleString("es-AR")}</strong></div>
        <div className="inventory-row"><span>Ejemplares totales</span><strong>{summary.total_copies.toLocaleString("es-AR")}</strong></div>
        <div className="inventory-row"><span>Disponibles para prestar</span><strong>{summary.available_copies.toLocaleString("es-AR")}</strong></div>
      </section>
      <section className="panel"><div className="panel-heading"><div><div className="eyebrow">MOVIMIENTO DE LA RED</div><h2>Circulación pendiente</h2></div></div>
        <div className="inventory-row"><span>Devoluciones en curso</span><strong>{summary.pending_returns}</strong></div>
        <div className="inventory-row"><span>Transferencias por despachar</span><strong>{summary.pending_dispatches}</strong></div>
        <div className="inventory-row"><span>Transferencias por recibir</span><strong>{summary.pending_arrivals}</strong></div>
        <p className="fine-print">Los traslados se ejecutan en el motor interbibliotecario. La gestión visual completa se incorpora en la siguiente fase.</p>
      </section>
    </div>
    <div className="notice"><strong>Información verificable</strong><span>Las cifras reflejan la base PostgreSQL de esta sucursal, no una simulación del navegador. La API requiere una identidad y permisos activos.</span></div>
  </main>;
}
