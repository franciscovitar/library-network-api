import { redirect } from "next/navigation";
import { staffApi } from "@/lib/api";
import type { StaffProfile } from "@/lib/types";

export const dynamic = "force-dynamic";
export default async function WorkspaceHome() {
  const profile = await staffApi<StaffProfile>("/api/v2/me");
  if (profile.branches.length === 0) {
    return (
      <main className="not-provisioned">
        <span className="eyebrow">IDENTIDAD VERIFICADA</span>
        <h1>Tu acceso está pendiente.</h1>
        <p>Tu sesión es válida, pero todavía no tenés permisos para operar ninguna sucursal. Un administrador debe autorizar tu acceso en el sistema.</p>
        <p className="small-note">No se crearon cuentas de personal ni datos por registrarte.</p>
      </main>
    );
  }
  redirect(`/workspace/${profile.branches[0].branch_id}`);
}
