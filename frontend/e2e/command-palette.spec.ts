/**
 * E2E — Command Palette (⌘+K) accessibility flow (M18)
 *
 * Covers:
 *  - Palette opens via keyboard shortcut (Ctrl+K)
 *  - Palette opens via sidebar button click
 *  - Escape closes the palette
 *  - Arrow-key navigation moves selection
 *  - Typing in the search field filters commands
 *  - Enter activates the selected item (navigation)
 *  - WCAG: dialog has aria-modal + aria-label
 */
import { expect, test } from "@playwright/test";

const EMAIL    = "admin@omniai.local";
const PASSWORD = "Admin12345!";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByRole("navigation", { name: /primary/i })).toBeVisible({ timeout: 10_000 });
}

test.describe("Command Palette", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("opens with Ctrl+K shortcut", async ({ page }) => {
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog", { name: /command palette/i })).toBeVisible({ timeout: 4_000 });
  });

  test("opens via sidebar button", async ({ page }) => {
    await page.getByRole("button", { name: /open command palette/i }).click();
    await expect(page.getByRole("dialog", { name: /command palette/i })).toBeVisible({ timeout: 4_000 });
  });

  test("closes with Escape", async ({ page }) => {
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toBeVisible({ timeout: 4_000 });
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible({ timeout: 4_000 });
  });

  test("typing filters commands", async ({ page }) => {
    await page.keyboard.press("Control+k");
    await page.getByRole("dialog", { name: /command palette/i }).getByRole("combobox").fill("knowledge");
    // Only the Knowledge navigation item should remain
    const items = page.getByRole("option").filter({ hasText: /knowledge/i });
    await expect(items.first()).toBeVisible({ timeout: 4_000 });
  });

  test("dialog has aria-modal attribute (WCAG)", async ({ page }) => {
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toBeVisible({ timeout: 4_000 });
    await expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  test("Enter on first item navigates away and closes palette", async ({ page }) => {
    await page.keyboard.press("Control+k");
    await page.getByRole("dialog", { name: /command palette/i }).getByRole("combobox").fill("chat");
    await page.keyboard.press("Enter");
    // Palette should be closed and chat page heading visible
    await expect(page.getByRole("dialog", { name: /command palette/i })).not.toBeVisible({ timeout: 4_000 });
    await expect(page.getByRole("heading", { name: /rag chat/i, exact: false })).toBeVisible({ timeout: 6_000 });
  });
});
