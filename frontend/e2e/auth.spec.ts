/**
 * E2E — Authentication flow (M18)
 *
 * Covers:
 *  - Login screen renders with email/password fields
 *  - Submitting valid credentials transitions to the main app
 *  - Invalid credentials shows an error alert
 *  - Sign-out returns to the login screen
 */
import { expect, test } from "@playwright/test";

const VALID_EMAIL    = "admin@omniai.local";
const VALID_PASSWORD = "Admin12345!";

test.describe("Authentication", () => {
  test("login screen renders required fields and sign-in button", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("valid credentials redirect to the main workspace", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel(/email/i).fill(VALID_EMAIL);
    await page.getByLabel(/password/i).fill(VALID_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    // After login the sidebar navigation should be visible
    await expect(page.getByRole("navigation", { name: /primary/i })).toBeVisible({ timeout: 10_000 });
  });

  test("invalid credentials show an error alert", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel(/email/i).fill("nobody@omniai.local");
    await page.getByLabel(/password/i).fill("wrong");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 8_000 });
  });

  test("sign-out returns to the login screen", async ({ page }) => {
    // Start by logging in
    await page.goto("/");
    await page.getByLabel(/email/i).fill(VALID_EMAIL);
    await page.getByLabel(/password/i).fill(VALID_PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByRole("navigation", { name: /primary/i })).toBeVisible({ timeout: 10_000 });

    // Sign out
    await page.getByRole("button", { name: /sign out/i }).click();
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible({ timeout: 8_000 });
  });
});
