import { expect, test } from "@playwright/test";

const root = "http://127.0.0.1:3000";

test("recruiter enters without login, lends/returns a real copy and stays isolated", async ({ browser }) => {
  const firstContext = await browser.newContext();
  const secondContext = await browser.newContext();
  try {
    const first = await firstContext.newPage();
    await first.goto(root);
    await expect(first.getByRole("heading", { name: /Cada libro/i })).toBeVisible();
    await first.getByRole("button", { name: /Explorar la biblioteca sin registrarte/ }).click();
    await expect(first).toHaveURL(/\/demo\/\d+(?:\?|$)/);
    await expect(first.getByText("Acceso público · sin login")).toBeVisible();
    const firstUrl = first.url();
    const stat = first.locator(".stat-grid .stat-card").first().locator(".stat-value");
    await expect(stat).toHaveText("0");

    await first.getByRole("button", { name: /Registrar préstamo/ }).click();
    await expect(first).toHaveURL(/notice=issued/);
    await expect(stat).toHaveText("1");
    const loanId = new URL(first.url()).searchParams.get("loan");
    expect(Number(loanId)).toBeGreaterThan(0);
    await expect(first.getByRole("button", { name: /Confirmar devolución/ })).toBeVisible();

    // A new recruiter's separate browser must not inherit the first workspace.
    const second = await secondContext.newPage();
    await second.goto(root);
    await second.getByRole("button", { name: /Explorar la biblioteca sin registrarte/ }).click();
    await expect(second).toHaveURL(/\/demo\/\d+(?:\?|$)/);
    expect(new URL(second.url()).pathname).not.toBe(new URL(firstUrl).pathname);
    await expect(second.locator(".stat-grid .stat-card").first().locator(".stat-value")).toHaveText("0");

    await first.reload();
    await expect(stat).toHaveText("1");
    await first.getByRole("button", { name: /Confirmar devolución/ }).click();
    await expect(first).toHaveURL(/notice=returned/);
    await expect(stat).toHaveText("0");
    await first.reload();
    await expect(stat).toHaveText("0");
    await expect(second.locator(".stat-grid .stat-card").first().locator(".stat-value")).toHaveText("0");

    // Browser-side cookie mutation cannot impersonate a valid server session.
    const cookies = await firstContext.cookies();
    const guest = cookies.find((cookie) => cookie.name === "library_guest");
    expect(guest).toBeDefined();
    if (!guest) throw new Error("guest cookie was not set");
    const suffix = guest.value.endsWith("A") ? "B" : "A";
    await firstContext.addCookies([{
      name: guest.name,
      value: guest.value.slice(0, -1) + suffix,
      url: root,
      sameSite: "Lax",
      httpOnly: true,
    }]);
    await first.goto(firstUrl);
    await expect(first).toHaveURL(root + "/");
  } finally {
    await firstContext.close();
    await secondContext.close();
  }
});
