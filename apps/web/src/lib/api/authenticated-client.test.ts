import { vi } from "vitest";

import {
  AuthenticatedApiClient,
  AuthenticatedApiError,
  type SessionTokenSource,
} from "@/lib/api/authenticated-client";

function tokens(values: Partial<SessionTokenSource> = {}): SessionTokenSource {
  return {
    getAccessToken: vi.fn(async () => "fresh-token"),
    refreshAccessToken: vi.fn(async () => null),
    invalidateSession: vi.fn(async () => undefined),
    ...values,
  };
}

test("adds the current Bearer token and preserves the exact body", async () => {
  let captured: RequestInit | undefined;
  const source = tokens();
  const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    captured = init;
    return new Response("{}", { status: 200 });
  });
  const client = new AuthenticatedApiClient(source, fetcher, "https://api.example.test");
  const body = JSON.stringify({ message: "مرحبا" });
  await client.request("/api/v1/me/advisor", { method: "POST", body });
  const headers = new Headers(captured?.headers);
  expect(headers.get("Authorization")).toBe("Bearer fresh-token");
  expect(captured?.body).toBe(body);
  expect(captured?.body).not.toContain("owner");
  expect(source.getAccessToken).toHaveBeenCalledTimes(1);
  expect(captured?.signal).toBeUndefined();
});

test("forwards an explicit feature deadline without creating one globally", async () => {
  const fetcher = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.signal).toBe(signal);
    return new Response("{}", { status: 200 });
  });
  const signal = AbortSignal.timeout(60_000);
  const client = new AuthenticatedApiClient(tokens(), fetcher, "https://api.example.test");
  await client.request("/api/v1/me/degree-paths", { method: "POST", signal });
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test("does not send a request when there is no current token", async () => {
  const fetcher = vi.fn();
  const client = new AuthenticatedApiClient(
    tokens({ getAccessToken: vi.fn(async () => null) }),
    fetcher,
    "https://api.example.test",
  );
  await expect(client.request("/api/v1/me/advisor")).rejects.toMatchObject({
    code: "UNAUTHENTICATED",
  });
  expect(fetcher).not.toHaveBeenCalled();
});

test("a 401 refreshes and retries at most once with a genuinely new token", async () => {
  const source = tokens({ refreshAccessToken: vi.fn(async () => "renewed-token") });
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response(null, { status: 401 }))
    .mockResolvedValueOnce(new Response(null, { status: 200 }));
  const client = new AuthenticatedApiClient(source, fetcher, "https://api.example.test");
  await client.request("/api/v1/me/academic-progress");
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(new Headers(fetcher.mock.calls[1][1]?.headers).get("Authorization")).toBe(
    "Bearer renewed-token",
  );
});

test("persistent 401 invalidates the session without a retry loop", async () => {
  const source = tokens({ refreshAccessToken: vi.fn(async () => "renewed-token") });
  const fetcher = vi.fn(async () => new Response(null, { status: 401 }));
  const client = new AuthenticatedApiClient(source, fetcher, "https://api.example.test");
  await expect(client.request("/api/v1/me/academic-progress")).rejects.toMatchObject({
    code: "UNAUTHENTICATED",
  });
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(source.invalidateSession).toHaveBeenCalledTimes(1);
});

test("a stale unchanged token is not retried", async () => {
  const source = tokens({ refreshAccessToken: vi.fn(async () => "fresh-token") });
  const fetcher = vi.fn(async () => new Response(null, { status: 401 }));
  const client = new AuthenticatedApiClient(source, fetcher, "https://api.example.test");
  await expect(client.request("/api/v1/me/academic-progress")).rejects.toBeInstanceOf(
    AuthenticatedApiError,
  );
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test.each([
  [403, "FORBIDDEN"],
  [422, "VALIDATION_ERROR"],
  [500, "SERVER_ERROR"],
  [503, "SERVICE_UNAVAILABLE"],
] as const)("maps HTTP %s without leaking response details", async (status, code) => {
  const client = new AuthenticatedApiClient(
    tokens(),
    vi.fn(async () => new Response("private stack", { status })),
    "https://api.example.test",
  );
  await expect(client.request("/api/v1/me/academic-progress")).rejects.toMatchObject({
    code,
    status,
    message: code,
  });
});

test("maps network failure safely", async () => {
  const client = new AuthenticatedApiClient(
    tokens(),
    vi.fn(async () => {
      throw new Error("private network detail");
    }),
    "https://api.example.test",
  );
  await expect(client.request("/api/v1/me/academic-progress")).rejects.toMatchObject({
    code: "NETWORK_ERROR",
    status: null,
  });
});

test("constructs exact production URLs for student endpoints", async () => {
  const urls: string[] = [];
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return new Response("{}", { status: 200 });
  });
  const client = new AuthenticatedApiClient(
    tokens(),
    fetcher,
    "https://morshidi.onrender.com",
  );
  await client.request("/api/v1/me/academic-profile");
  await client.request("/api/v1/me/academic-progress");
  expect(urls).toEqual([
    "https://morshidi.onrender.com/api/v1/me/academic-profile",
    "https://morshidi.onrender.com/api/v1/me/academic-progress",
  ]);
});

test("normalizes baseUrl with trailing slashes", async () => {
  const urls: string[] = [];
  const fetcher = vi.fn(async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return new Response("{}", { status: 200 });
  });
  const client = new AuthenticatedApiClient(
    tokens(),
    fetcher,
    "https://morshidi.onrender.com///",
  );
  await client.request("/api/v1/me/academic-profile");
  expect(urls[0]).toBe("https://morshidi.onrender.com/api/v1/me/academic-profile");
});

test("invokes fetcher bound to globalThis avoiding Illegal invocation", async () => {
  let invoked = false;
  const fakeFetch = function (this: unknown) {
    invoked = true;
    expect(this).toBe(globalThis);
    return Promise.resolve(new Response("{}", { status: 200 }));
  };
  const client = new AuthenticatedApiClient(tokens(), fakeFetch, "https://api.example.test");
  await client.request("/api/v1/me/academic-profile");
  expect(invoked).toBe(true);
});
