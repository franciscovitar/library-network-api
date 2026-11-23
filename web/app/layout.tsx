import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Library Network", template: "%s · Library Network" },
  description: "Gestión operativa de bibliotecas. Catálogo y circulación respaldados por PostgreSQL.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es-AR">
      <body>{children}</body>
    </html>
  );
}
