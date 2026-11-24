"use client";
import { useSyncExternalStore } from "react";
import Link from "next/link";
import type { GuestProfile } from "@/lib/guest-types";
import { shortBranch } from "@/lib/guest-display";

function subscribeHash(callback: () => void) {
  window.addEventListener("hashchange", callback);
  window.addEventListener("popstate", callback);
  return () => { window.removeEventListener("hashchange", callback); window.removeEventListener("popstate", callback); };
}
const getHash = () => window.location.hash;
const serverHash = () => "";

export default function GuestNav({ profile, branch, transfers = false }: { profile: GuestProfile; branch: number; transfers?: boolean }) {
  const root = `/demo/${branch}`;
  const hash = useSyncExternalStore(subscribeHash, getHash, serverHash);
  const sections = ["#resumen", "#catalogo", "#prestamos", "#devoluciones"];
  const active = transfers ? 4 : Math.max(0, sections.indexOf(hash));
  const items = [["⌂", "Resumen"], ["▤", "Catálogo"], ["↗", "Préstamos"], ["↙", "Devoluciones"], ["⇄", "Traslados"]];
  return <aside className="sidebar guest-sidebar">
    <Link href="/" className="sidebar-brand"><span className="brand-mark">ln<span>·</span></span> Library Network</Link>
    <div className="sidebar-label">GESTIÓN DE BIBLIOTECA</div>
    <nav className="sidebar-nav" aria-label="Operaciones">
      {items.map(([icon, label], index) => {
        const className = `nav-link ${active === index ? "guest-nav-current" : ""}`;
        const content = <><span aria-hidden="true">{icon}</span>{label}</>;
        // Native anchors preserve history, emit hashchange and retain the current query.
        if (!transfers && index < 4) return <a key={label} className={className} href={sections[index]} aria-current={active === index ? "location" : undefined}>{content}</a>;
        return <Link key={label} className={className} href={index === 4 ? root + "/transfers" : root + sections[index]} aria-current={active === index ? "page" : undefined}>{content}</Link>;
      })}
    </nav>
    <div className="guest-branches"><div className="sidebar-label">SUCURSAL ACTUAL</div><nav className="guest-branch-list" aria-label="Cambiar sucursal">
      {profile.branches.map(b => <Link key={b.branch_id} className={`branch-link ${b.branch_id === branch ? "selected" : ""}`} aria-current={b.branch_id === branch ? "location" : undefined} href={`/demo/${b.branch_id}${transfers ? "/transfers" : ""}`}>{shortBranch(b.name)}{b.branch_id === branch && <span aria-hidden="true"> ✓</span>}</Link>)}
    </nav></div>
    <div className="sidebar-bottom"><div className="workspace-note"><strong>Modo demostración</strong><span>Datos ficticios. Tu biblioteca es independiente y temporal.</span></div></div>
  </aside>;
}
