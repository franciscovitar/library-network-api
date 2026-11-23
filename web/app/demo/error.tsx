"use client";
import Link from "next/link";
export default function DemoError({ reset }: { error: Error; reset: () => void }) {
  return <main className="error-screen"><div><div className="eyebrow">ESPACIO TEMPORAL</div><h1>No pudimos abrir tu biblioteca.</h1><p>Si tu espacio expiró, podés comenzar uno nuevo sin registrarte.</p><button type="button" onClick={reset} className="button button-primary">Reintentar</button> <Link href="/" className="button button-outline">Ir al inicio</Link></div></main>;
}
