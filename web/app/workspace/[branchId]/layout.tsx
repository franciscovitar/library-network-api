import Link from "next/link";
import { notFound } from "next/navigation";
import { signOut } from "@/auth";
import { staffApi } from "@/lib/api";
import { positiveId } from "@/lib/input";
import type { BranchAccess, StaffProfile } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function BranchLayout({ children, params }: {
  children: React.ReactNode;
  params: Promise<{ branchId: string }>;
}) {
  const { branchId: raw } = await params;
  const branchId = positiveId(raw);
  if (!branchId) notFound();
  const profile = await staffApi<StaffProfile>("/api/v2/me");
  const current = profile.branches.find((b) => b.branch_id === branchId);
  if (!current) notFound();
  const root = `/workspace/${branchId}`;
  const entries = [
    { href: root, name: "Resumen", symbol: "◫" },
    { href: `${root}/catalog`, name: "Catálogo", symbol: "▤" },
    { href: `${root}/circulation`, name: "Circulación", symbol: "⇄" },
  ];
  const roleNames: Record<BranchAccess["role"], string> = {
    VIEWER: "Consulta", LIBRARIAN: "Bibliotecario",
    BRANCH_MANAGER: "Responsable de sede", NETWORK_ADMIN: "Administrador",
  };
  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <Link className="sidebar-brand" href="/workspace"><span className="brand-mark">ln<span>·</span></span> Library Network</Link>
        <div className="sidebar-label">ESPACIO DE TRABAJO</div>
        <nav aria-label="Navegación principal" className="sidebar-nav">
          {entries.map((entry) => <Link key={entry.name} href={entry.href} className="nav-link"><span aria-hidden="true">{entry.symbol}</span>{entry.name}</Link>)}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-note"><strong>Operación real</strong><span>Datos sintéticos en desarrollo</span></div>
          <form action={async () => { "use server"; await signOut({ redirectTo: "/" }); }}>
            <button type="submit" className="signout-button">Cerrar sesión <span aria-hidden="true">↗</span></button>
          </form>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="workspace-header">
          <div className="breadcrumb"><span>Red de bibliotecas</span><span aria-hidden="true">/</span><strong>{current.branch_name}</strong></div>
          <div className="header-tools"><span className="role-badge">{roleNames[current.role]}</span><span className="identity-chip">Sesión verificada</span></div>
        </header>
        <div className="workspace-content">
          {profile.branches.length > 1 && <div className="branch-picker"><span>Sucursales autorizadas:</span>{profile.branches.map((b) => (
            <Link className={b.branch_id === branchId ? "branch-link selected" : "branch-link"} href={`/workspace/${b.branch_id}`} key={b.branch_id}>{b.branch_name}</Link>
          ))}</div>}
          {children}
        </div>
      </div>
    </div>
  );
}
