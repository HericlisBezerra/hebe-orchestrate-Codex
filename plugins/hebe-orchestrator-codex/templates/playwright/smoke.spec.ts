import { expect, test } from "@playwright/test";

test("a página inicial abre sem erros de execução", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();
  await expect(page.locator("body")).not.toHaveText(/^\s*$/);
  expect(pageErrors).toEqual([]);
});

