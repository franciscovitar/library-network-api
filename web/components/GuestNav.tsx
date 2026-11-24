import Link from "next/link";
import type { GuestProfile } from "@/lib/guest-types";
import { shortBranch } from "@/lib/guest-display";

export default function GuestNav({ profile, branch, transfers = false }: { profile: GuestProfile; branch: number; transfers?: boolean }) {
  const root = `/demo/${branch}`;
  const items = [["⌂", "Resumen", root], ["▤", "Catálogo", root + "#catalogo"], ["↗", "Préstamos", root + "#prestamos"], ["↙", "Devoluciones", root + "#devoluciones"], ["⇄", "Traslados", root + "/transfers"]];
  return <aside className="sidebar guest-sidebar">
    <Link href="/" className="sidebar-brand"><span className="brand-mark">ln<span>·</span></span> Library Network</Link>
    <div className="sidebar-label">GESTIÓN DE BIBLIOTECA</div>
    <nav className="sidebar-nav" aria-label="Operaciones">
      {items.map(([icon, label, href], index) => <Link key={label} className={`nav-link ${(transfers ? index === 4 : index === 0) ? "guest-nav-current" : ""}`} href={href} aria-current={(transfers ? index === 4 : index === 0) ? "page" : undefined}><span aria-hidden="true">{icon}</span>{label}</Link>)}
    </nav>
    <div className="guest-branches"><div className="sidebar-label">SUCURSAL ACTUAL</div><nav className="guest-branch-list" aria-label="Cambiar sucursal">
      {profile.branches.map(b => <Link key={b.branch_id} className={`branch-link ${b.branch_id === branch ? "selected" : ""}`} aria-current={b.branch_id === branch ? "location" : undefined} href={`/demo/${b.branch_id}${transfers ? "/transfers" : ""}`}>{shortBranch(b.name)}{b.branch_id === branch && <span aria-hidden="true"> ✓</span>}</Link>)}
    </nav></div>
    <div className="sidebar-bottom"><div className="workspace-note"><strong>Modo demostración</strong><span>Datos ficticios. Tu biblioteca es independiente y temporal.</span></div></div>
  </aside>;
}
