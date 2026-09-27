import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("attaches the access token as a Bearer header", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) =>
        new Response(JSON.stringify({ id: "v1", vault_addr: "0xabc" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.getMyVault("token-123");

    const [, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer token-123");
  });

  it("throws ApiError with the status code on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("vault not found", { status: 404 })),
    );

    await expect(api.getMyVault("token-123")).rejects.toMatchObject({
      status: 404,
    } satisfies Partial<ApiError>);
  });
});
