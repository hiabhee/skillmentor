import { afterEach, describe, expect, it, vi } from "vitest";
import { api, feedbackObject } from "@/lib/api";

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "skillmentor_csrf=; Max-Age=0; path=/";
});

describe("API client", () => {
  it("sends the readable CSRF cookie as a header for mutations", async () => {
    document.cookie = "skillmentor_csrf=csrf-value; path=/";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await api("/profile", { method: "PUT", body: JSON.stringify({ name: "Ada" }) });
    const options = fetchMock.mock.calls[0][1];
    expect((options?.headers as Headers).get("x-csrf-token")).toBe("csrf-value");
    expect(options?.credentials).toBe("same-origin");
    expect(options?.cache).toBe("no-store");
  });

  it("lets the browser set the multipart boundary for FormData uploads", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ transcript: "hi" }), { status: 200 }));
    const form = new FormData(); form.append("audio", new Blob(["x"], { type: "audio/webm" }), "answer.webm");
    await api("/interviews/1/transcriptions", { method: "POST", body: form });
    expect((fetchMock.mock.calls[0][1]?.headers as Headers).has("content-type")).toBe(false);
  });

  it("surfaces structured API errors with their status", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "unauthorized", message: "Sign in first." } }), { status: 401 }));
    await expect(api("/dashboard")).rejects.toMatchObject({ status: 401, code: "unauthorized", message: "Sign in first." });
  });

  it("parses stored feedback and tolerates legacy plain text", () => {
    expect(feedbackObject('{"summary":"Clear answer","score":8}')).toMatchObject({ summary: "Clear answer", score: 8 });
    expect(feedbackObject("Old feedback text")).toMatchObject({ summary: "Old feedback text" });
    expect(feedbackObject(null)).toBeNull();
  });
});
