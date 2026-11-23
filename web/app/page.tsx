import Link from "next/link";
import { enterDemo } from "@/app/demo/actions";

export default function Home() {
  return (
    <main className="landing">
      <div className="landing-frame">
        <header className="public-header"><span className="brand-mark">ln<span>·</span></span><span>Library Network</span><span className="public-nav">Gestión bibliotecaria</span></header>
        <div className="landing-grid">
          <section>
            <div className="eyebrow">PLATAFORMA DE OPERACIONES BIBLIOTECARIAS</div>
            <h1>Cada libro,<br /><em>en su lugar.</em></h1>
            <p className="landing-lede">Una plataforma para conectar catálogos, ejemplares y circulación entre sucursales. Menos tareas repetitivas. Más tiempo para las personas.</p>
            <form action={enterDemo}><button type="submit" className="button button-primary">Explorar la biblioteca sin registrarte <span aria-hidden="true">↗</span></button></form>
            <p className="small-note">No necesitás cuenta ni contraseña. El sistema asigna un espacio temporal con datos sintéticos y operaciones reales.</p>
            <Link href="/login" className="link-muted">Acceso para personal autorizado</Link>
          </section>
          <div className="landing-art" aria-hidden="true">
            <div className="landing-book book-a" /><div className="landing-book book-b" /><div className="landing-book book-c" />
            <span className="art-caption">Una red de conocimiento en movimiento.</span>
          </div>
        </div>
        <footer className="public-footer">LIBRARY NETWORK <span>Un producto en desarrollo · Sin datos de bibliotecas reales</span></footer>
      </div>
    </main>
  );
}
