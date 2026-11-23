import { expect, test } from "@playwright/test";

test("starting another anonymous library preserves prior PostgreSQL records without reusing its cookie", async ({ browser }) => {
  const activeContext = await browser.newContext();
  const previousContext = await browser.newContext();
  try {
    const page = await activeContext.newPage();
    await page.goto("/");
    await page.getByRole("button", { name: /Explorar la biblioteca sin registrarte/ }).click();
    await expect(page).toHaveURL(/\/demo\/\d+(?:\?|$)/);
    const previousUrl = new URL(page.url()).origin + new URL(page.url()).pathname;

    await page.getByRole("button", { name: /Registrar préstamo/ }).click();
    await expect(page).toHaveURL(/notice=issued/);
    await expect(page.locator(".stat-grid .stat-card").first().locator(".stat-value")).toHaveText("1");

    const originalCookie = (await activeContext.cookies()).find((c) => c.name === "library_guest");
    expect(originalCookie).toBeDefined();
    if (!originalCookie) throw new Error("Original browser capability missing");

    await page.getByRole("button", { name: "Crear otra biblioteca temporal" }).click();
    await expect(page).toHaveURL(/\/demo\/\d+(?:\?|$)/);
    expect(new URL(page.url()).pathname).not.toBe(new URL(previousUrl).pathname);
    await expect(page.locator(".stat-grid .stat-card").first().locator(".stat-value")).toHaveText("0");

    const newCookie = (await activeContext.cookies()).find((c) => c.name === "library_guest");
    expect(newCookie).toBeDefined();
    expect(newCookie?.value).not.toBe(originalCookie.value);

    // Switching the active browser does not erase records held by the old
    // capability. Retention and revocation require a separate cleanup policy.
    await previousContext.addCookies([{
      name: originalCookie.name,
      value: originalCookie.value,
      url: "http://127.0.0.1:3000",
      httpOnly: true,
      sameSite: "Lax",
    }]);
    const priorPage = await previousContext.newPage();
    await priorPage.goto(previousUrl);
    await expect(priorPage.locator(".stat-grid .stat-card").first().locator(".stat-value")).toHaveText("1");
    await page.reload();
    await expect(page.locator(".stat-grid .stat-card").first().locator(".stat-value")).toHaveText("0");
  } finally {
    await previousContext.close();
    await activeContext.close();
  }
});
