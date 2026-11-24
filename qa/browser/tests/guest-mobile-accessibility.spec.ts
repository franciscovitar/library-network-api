import { expect, test } from "@playwright/test";

const root = "http://127.0.0.1:3000";

test.use({
  viewport: { width: 390, height: 844 },
  isMobile: true,
  hasTouch: true,
  deviceScaleFactor: 3,
});

test("guest journey fits a mobile viewport and works from the keyboard", async ({ page }) => {
  await page.goto(root);
  await expect(page.getByRole("heading", { name: /Cada libro/i })).toBeVisible();
  await expect(page.getByRole("main")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  const enterLibrary = page.getByRole("button", { name: /Explorar la biblioteca sin registrarte/ });
  await enterLibrary.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/demo\/\d+(?:\?|$)/);
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByLabel("Socio", { exact: true })).toBeVisible();
  await expect(page.locator("#guest-member option").first()).toHaveText(/Sofía Martínez/);
  const nav = page.getByRole("navigation", { name: "Operaciones" });
  await expect(nav).toBeVisible();
  await expect(nav.getByRole("link", { name: "Resumen" })).toHaveAttribute("aria-current", "location");
  for (const name of ["Catálogo", "Préstamos", "Devoluciones"]) {
    await nav.getByRole("link", { name, exact: true }).click();
    await expect(nav.getByRole("link", { name, exact: true })).toHaveClass(/guest-nav-current/);
    await expect(nav.locator("[aria-current]")).toHaveCount(1);
  }
  await page.goBack();
  await expect(nav.getByRole("link", { name: "Préstamos", exact: true })).toHaveAttribute("aria-current", "location");
  await page.getByRole("link", { name: /Buscar libro/ }).click();
  await expect(nav.getByRole("link", { name: "Catálogo", exact: true })).toHaveAttribute("aria-current", "location");
  await expect(page.getByLabel(/ejemplar disponible/i)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  const issueLoan = page.getByRole("button", { name: /Registrar préstamo/ });
  await issueLoan.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/notice=issued/);
  await expect(page.getByRole("button", { name: /Confirmar devolución/ })).toBeVisible();
});
