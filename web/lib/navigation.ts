/** Only known UI statuses are reflected into URLs and visible confirmations. */
export function feedback(key: string | undefined): { tone: "success" | "error"; text: string } | null {
  switch (key) {
    case "issued": return { tone: "success", text: "Préstamo registrado en la base de datos." };
    case "returned": return { tone: "success", text: "Devolución confirmada y ejemplar actualizado." };
    case "invalid": return { tone: "error", text: "Revisá los identificadores y volvé a intentar." };
    case "denied": return { tone: "error", text: "Tu cuenta no tiene permisos para esa operación." };
    case "conflict": return { tone: "error", text: "El estado cambió o el ejemplar no está disponible. Actualizá la página." };
    case "unavailable": return { tone: "error", text: "No se pudo confirmar la operación. Volvé a intentar." };
    default: return null;
  }
}
