import Link from "next/link";
import { signIn } from "@/auth";

export const metadata = { title: "Ingresar" };

export default function LoginPage() {
  return (
    <main className="login-screen">
      <div className="login-panel">
        <Link href="/" className="brand-link"><span className="brand-mark">ln<span>·</span></span> Library Network</Link>
        <span className="eyebrow">ACCESO DE PERSONAL</span>
        <h1>Bienvenido de nuevo.</h1>
        <p>Iniciá sesión con tu identidad de GitHub. La aplicación comprobará después tus permisos para cada sucursal directamente en la base de datos.</p>
        <form action={async () => { "use server"; await signIn("github", { redirectTo: "/workspace" }); }}>
          <button className="button button-primary full-width" type="submit">Continuar con GitHub <span aria-hidden="true">↗</span></button>
        </form>
        <div className="login-help">No se conceden permisos automáticamente por iniciar sesión. Si todavía no tenés una sucursal asignada, verás un estado de acceso pendiente.</div>
        <Link href="/" className="link-muted">← Volver al inicio</Link>
      </div>
    </main>
  );
}
