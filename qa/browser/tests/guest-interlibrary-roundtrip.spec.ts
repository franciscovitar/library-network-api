import { expect, test } from "@playwright/test";

test("a recruiter completes real cross-branch logistics without creating an account", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Explorar la biblioteca sin registrarte/ }).click();
  await expect(page).toHaveURL(/\/demo\/\d+(?:\?|$)/);

  await page.getByRole("link", { name: /Operaciones entre sedes/ }).click();
  await expect(page.getByRole("heading", { name: /Un libro,/ })).toBeVisible();
  await page.getByRole("button", { name: /Solicitar traslado/ }).click();
  await expect(page).toHaveURL(/notice=requested/);
  await expect(page.getByRole("heading", { name: /Préstamos entre sedes/ })).toBeVisible();
  await expect(page.locator(".transfer-item").first()).toContainText("Solicitud registrada");

  await page.getByRole("button", { name: /Confirmar despacho/ }).click();
  await expect(page).toHaveURL(/notice=advanced/);
  await expect(page.locator(".transfer-item").first()).toContainText("Despachado");
  await page.reload();
  await expect(page.getByRole("button", { name: /Marcar en tránsito/ })).toBeVisible();
  await page.getByRole("button", { name: /Marcar en tránsito/ }).click();
  await expect(page.locator(".transfer-item").first()).toContainText("En tránsito");
  await page.getByRole("button", { name: /Confirmar recepción/ }).click();
  await expect(page.locator(".transfer-item").first()).toContainText("Recibido");
  await page.getByRole("button", { name: /Activar préstamo recibido/ }).click();
  await expect(page).toHaveURL(/notice=activated/);
  await expect(page.locator(".transfer-item").first()).toContainText("Préstamo activo");
  await page.getByRole("button", { name: /Registrar devolución/ }).click();
  await expect(page).toHaveURL(/notice=returned/);
  await expect(page.locator(".transfer-item").first()).toContainText("Devolución en camino");

  await page.getByRole("button", { name: /Confirmar despacho/ }).click();
  await page.getByRole("button", { name: /Marcar en tránsito/ }).click();
  await page.getByRole("button", { name: /Confirmar recepción/ }).click();
  await expect(page.locator(".transfer-item").first()).toContainText("Operación completada");
  await page.reload();
  await expect(page.locator(".transfer-item").first()).toContainText("Operación completada");
});
