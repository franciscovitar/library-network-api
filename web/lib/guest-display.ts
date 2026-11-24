/** Synthetic display labels; the original ID is always submitted to the server. */
const names: Record<string, string> = {
  "01": "Sofía Martínez", "02": "Tomás Fernández", "03": "Valentina García",
};
export function memberLabel(code: string): string {
  const number = /-M(\d+)$/.exec(code)?.[1];
  if (!number) return "Socio de prueba";
  return names[number] ? `${names[number]} · Socio ${number}` : `Socio ${number}`;
}
export function copyLabel(code: string): string {
  const number = /-C(\d+)$/.exec(code)?.[1];
  return number ? `Ejemplar ${number}` : "Ejemplar de prueba";
}
export function shortBranch(name: string): string { return name.split("· ").at(-1) ?? name; }
export function loanStatus(status: string): string {
  const labels: Record<string, string> = { REQUESTED: "Solicitado", ACTIVE: "Activo", RETURNING: "En devolución", CLOSED: "Devuelto" };
  return Object.hasOwn(labels, status) ? labels[status] : "Consultar estado";
}
export function dateLabel(value: string | null): string {
  if (!value) return "Sin fecha";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Sin fecha" : new Intl.DateTimeFormat("es-AR", { dateStyle: "medium", timeZone: "America/Argentina/Cordoba" }).format(date);
}
