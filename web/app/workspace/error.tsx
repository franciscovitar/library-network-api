"use client";

export default function WorkspaceError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="error-screen">
      <span className="eyebrow">SERVICIO TEMPORALMENTE NO DISPONIBLE</span>
      <h1>No pudimos cargar tu espacio.</h1>
      <p>Verificá que la aplicación y el servicio de bibliotecas estén configurados y volvé a intentar.</p>
      <button type="button" className="button button-primary" onClick={reset}>Reintentar</button>
    </main>
  );
}
