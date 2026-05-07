/**
 * E2E — Agent builder & run export flow (M18)
 *
 * Covers:
 *  - Agents page loads with heading
 *  - Create agent form has name + description fields
 *  - Export run buttons appear when a run is present
 *  - Canvas renders at least the default Start → End nodes
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

test.describe("Agents page", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.getByRole("navigation", { name: /Primary/i }).getByRole("link", { name: /Workflows/i, exact: true }).click();
    await expect(page.getByRole("heading", { name: /agent runtime/i, exact: false })).toBeVisible();
  });

  test("create-agent form has required name field", async ({ page }) => {
    await expect(page.getByRole("textbox", { name: /^name/i }).first()).toBeVisible();
    const createBtn = page.getByRole("button", { name: /^create$/i });
    await expect(createBtn).toBeDisabled();
    await page.getByRole("textbox", { name: /^name/i }).first().fill("My agent");
    await expect(createBtn).toBeEnabled();
  });

  test("canvas renders at least Start and End nodes", async ({ page }) => {
    // Stub agents list with one agent that has default nodes
    await page.route("**/v1/agents*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "agent-001",
            name: "Demo agent",
            description: "",
            published: false,
            definition: {
              version: 1,
              nodes: [
                { id: "start",      type: "start",      label: "Start" },
                { id: "retrieval",  type: "retrieval",  label: "Retrieve" },
                { id: "generate",   type: "generate",   label: "Generate" },
                { id: "end",        type: "end",        label: "End" },
              ],
              edges: [],
              collectionIds: [],
            },
          },
        ]),
      });
    });
    await page.route("**/v1/agents/agent-001/runs*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.reload();
    const canvas = page.getByLabel("Agent graph canvas");
    await expect(canvas).toBeVisible({ timeout: 8_000 });
    await expect(canvas.getByText("Start").first()).toBeVisible();
    await expect(canvas.getByText("End").first()).toBeVisible();
  });

  test("export run buttons appear when latest run exists", async ({ page }) => {
    await page.route("**/v1/agents*", async (route) => {
      if (route.request().url().endsWith("/agents")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            { id: "agent-002", name: "Agent", description: "", published: false,
              definition: { version: 1, nodes: [], edges: [], collectionIds: [] } },
          ]),
        });
      } else {
        await route.continue();
      }
    });
    await page.route("**/v1/agents/agent-002/runs*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "run-001",
            agent_id: "agent-002",
            status: "COMPLETED",
            input: "Hello",
            output: { answer: "World" },
            events: [],
            created_at: new Date().toISOString(),
          },
        ]),
      });
    });

    await page.reload();
    await expect(page.getByTitle(/export run as markdown/i)).toBeVisible({ timeout: 8_000 });
    await expect(page.getByTitle(/export run as json/i)).toBeVisible();
  });
});
