import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { POST, GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("same-origin backend proxy", () => {
  it("forwards the session boundary and preserves API cookies", async () => {
    vi.stubEnv("BACKEND_URL", "private-api.internal:10000");
    const upstreamHeaders = new Headers({ "content-type": "application/json" });
    upstreamHeaders.append("set-cookie", "skillmentor_session=secret; HttpOnly; Path=/; SameSite=Lax");
    upstreamHeaders.append("set-cookie", "skillmentor_csrf=csrf; Path=/; SameSite=Lax");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 201, headers: upstreamHeaders }));
    const request = new NextRequest("http://localhost/api/v1/auth/register", {
      method: "POST",
      headers: { "content-type": "application/json", cookie: "skillmentor_csrf=csrf", origin: "http://localhost:3000", "x-csrf-token": "csrf" },
      body: JSON.stringify({ email: "person@example.com" }),
    });
    const response = await POST(request, { params: Promise.resolve({ path: ["auth", "register"] }) });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://private-api.internal:10000/api/v1/auth/register");
    const forwarded = init?.headers as Headers;
    expect(forwarded.get("cookie")).toBe("skillmentor_csrf=csrf");
    expect(forwarded.get("origin")).toBe("http://localhost:3000");
    expect(forwarded.get("x-csrf-token")).toBe("csrf");
    expect(await new Response(init?.body ?? null).text()).toContain("person@example.com");
    expect(response.status).toBe(201);
    expect(response.headers.getSetCookie()).toHaveLength(2);
  });

  it("converts backend network failures into a no-store 503", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("connection refused"));
    const request = new NextRequest("http://localhost/api/v1/health/ready", { method: "POST", headers: { origin: "http://localhost:3000" } });
    const response = await POST(request, { params: Promise.resolve({ path: ["health", "ready"] }) });
    expect(response.status).toBe(503);
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect((await response.json()).error.code).toBe("upstream_unavailable");
  });

  it("rejects traversal paths without contacting the backend", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const request = new NextRequest("http://localhost/api/v1/health/live");
    const response = await GET(request, { params: Promise.resolve({ path: ["..", "health", "live"] }) });
    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
