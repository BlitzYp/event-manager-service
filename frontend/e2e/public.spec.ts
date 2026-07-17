import { expect, test } from "@playwright/test";

test("public landing page links to both operational surfaces", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /run event spending/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /administrator/i })).toHaveAttribute("href", "/admin");
  await expect(page.getByRole("link", { name: /vendor wallet/i })).toHaveAttribute("href", "/wallet");
});

