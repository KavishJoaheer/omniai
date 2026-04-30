/**
 * Tests for the API client.
 *
 * Covers envelope unwrapping, error propagation, and request shape for the
 * most-used endpoints.  Network calls are stubbed via global.fetch.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";

const okEnvelope = <T>(data: T) => ({ code: 0, message: "ok", data });

beforeEach(() => {
  global.fetch = vi.fn();
  if (typeof window !== "undefined") {
    window.localStorage.clear();
  }
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockJson<T>(payload: T, status = 200) {
  (global.fetch as any).mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  });
}

describe("api client — envelope unwrapping", () => {
  it("unwraps Envelope<T>.data on success (health)", async () => {
    mockJson(okEnvelope({ name: "Omni-AI", status: "healthy", environment: "dev" }));
    const result = await api.health();
    expect(result.status).toBe("healthy");
    expect(result.environment).toBe("dev");
  });

  it("throws on non-2xx responses", async () => {
    mockJson({ code: -1, message: "boom" }, 500);
    await expect(api.health()).rejects.toThrow();
  });

  it("login posts JSON to /v1/auth/login", async () => {
    mockJson(
      okEnvelope({
        accessToken: "tok-123",
        sessionTtlMinutes: 60,
        principal: {
          userId: "u1",
          email: "a@b.com",
          displayName: "Alice",
          tenantId: "t1",
          tenantName: "T1",
          role: "OWNER",
        },
      }),
    );

    const result = await api.login("a@b.com", "password");
    expect(result.accessToken).toBe("tok-123");
    expect(result.principal.role).toBe("OWNER");

    const call = (global.fetch as any).mock.calls[0];
    expect(call[0]).toContain("/v1/auth/login");
    expect(call[1].method).toBe("POST");
    const body = JSON.parse(call[1].body);
    expect(body.email).toBe("a@b.com");
    expect(body.password).toBe("password");
  });

  it("listCollections sends GET to /v1/collections", async () => {
    mockJson(okEnvelope([]));
    await api.listCollections();
    const call = (global.fetch as any).mock.calls[0];
    expect(call[0]).toContain("/v1/collections");
  });

  it("createCollection posts the payload", async () => {
    mockJson(
      okEnvelope({
        id: "c1",
        tenant_id: "t1",
        name: "Docs",
        description: null,
        embedding_model: "nomic-embed-text",
        chunk_template: "general",
        system_prompt: null,
        top_k: 8,
        vector_weight: 0.6,
        document_count: 0,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      }),
    );
    const c = await api.createCollection({
      name: "Docs",
      embedding_model: "nomic-embed-text",
      chunk_template: "general",
    });
    expect(c.name).toBe("Docs");
  });

  it("deleteCollection sends DELETE", async () => {
    mockJson(okEnvelope({ deleted: "c1" }));
    await api.deleteCollection("c1");
    const call = (global.fetch as any).mock.calls[0];
    expect(call[1].method).toBe("DELETE");
    expect(call[0]).toContain("/v1/collections/c1");
  });

  it("logout sends POST", async () => {
    mockJson(okEnvelope({ loggedOut: true }));
    await api.logout();
    const call = (global.fetch as any).mock.calls[0];
    expect(call[0]).toContain("/v1/auth/logout");
    expect(call[1].method).toBe("POST");
  });
});
