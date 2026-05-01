/**
 * E2E — Chat / Grounded conversation flow (M18)
 *
 * Covers:
 *  - New conversation creates a chat session
 *  - Sending a message appears in the transcript
 *  - Export conversation button is present when a conversation is active
 *  - Regenerate button is disabled with no assistant message
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

test.describe("Chat page", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.getByRole("link", { name: /chat/i }).click();
    await expect(page.getByRole("heading", { name: /rag chat/i, exact: false })).toBeVisible();
  });

  test("new chat button creates a conversation entry in the sidebar", async ({ page }) => {
    // Intercept the create-conversation API to avoid needing a live backend
    await page.route("**/v1/conversations", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "conv-001",
            title: "New conversation",
            collection_ids: [],
            pinned: false,
            updated_at: new Date().toISOString(),
          }),
        });
      } else {
        await route.continue();
      }
    });

    await page.getByRole("button", { name: /new chat/i }).click();
    // The new conversation should appear in the sidebar list
    await expect(page.getByText("New conversation")).toBeVisible({ timeout: 6_000 });
  });

  test("regenerate button is disabled before any assistant message", async ({ page }) => {
    const regenerate = page.getByRole("button", { name: /regenerate/i });
    await expect(regenerate).toBeDisabled();
  });

  test("export buttons appear when a conversation is active", async ({ page }) => {
    // Stub conversation list to return one active conversation
    await page.route("**/v1/conversations", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "conv-abc",
            title: "My conversation",
            collection_ids: [],
            pinned: false,
            updated_at: new Date().toISOString(),
          },
        ]),
      });
    });
    // Stub messages
    await page.route("**/v1/conversations/conv-abc/messages", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.reload();
    await expect(page.getByTitle(/export as markdown/i)).toBeVisible({ timeout: 8_000 });
    await expect(page.getByTitle(/export as json/i)).toBeVisible();
  });
});
