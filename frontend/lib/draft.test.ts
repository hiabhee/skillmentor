import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDraft } from "@/lib/draft";

const ok = () => new Response(JSON.stringify({ saved: true }), { status: 200 });

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

function sentBodies(fetchMock: { mock: { calls: unknown[][] } }) {
  return fetchMock.mock.calls.map(([url, options]) => ({ url, body: JSON.parse(String((options as RequestInit).body)) }));
}

describe("useDraft", () => {
  it("starts from the server's saved draft", () => {
    const { result } = renderHook(() => useDraft(7, 2, "Saved on the server"));
    expect(result.current.text).toBe("Saved on the server");
  });

  it("saves the latest text once typing pauses", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => ok());
    const { result } = renderHook(() => useDraft(7, 2, ""));
    act(() => { result.current.setText("I would"); result.current.setText("I would cache it"); });
    expect(fetchMock).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(800); });
    expect(sentBodies(fetchMock)).toEqual([{ url: "/api/v1/interviews/7/draft", body: { position: 2, text: "I would cache it" } }]);
    expect(result.current.state).toBe("saved");
  });

  it("saves pending text when the question changes or the view unmounts", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => ok());
    const { result, unmount } = renderHook(() => useDraft(7, 2, ""));
    act(() => result.current.setText("Leaving mid-answer"));
    await act(async () => { unmount(); await Promise.resolve(); });
    expect(sentBodies(fetchMock)[0].body).toEqual({ position: 2, text: "Leaving mid-answer" });
  });

  it("does not save after the answer is submitted and cleared", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => ok());
    const { result } = renderHook(() => useDraft(7, 2, ""));
    act(() => { result.current.setText("Final answer"); result.current.clear(); });
    await act(async () => { await vi.advanceTimersByTimeAsync(800); });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.text).toBe("");
  });

  it("treats an already-answered question as nothing to save, and reports real failures", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: "stale_draft" } }), { status: 409 }));
    const { result } = renderHook(() => useDraft(7, 2, ""));
    act(() => result.current.setText("Too late"));
    await act(async () => { await vi.advanceTimersByTimeAsync(800); });
    expect(result.current.state).toBe("idle");

    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 500 }));
    act(() => result.current.setText("Server down"));
    await act(async () => { await vi.advanceTimersByTimeAsync(800); });
    expect(result.current.state).toBe("error");
  });
});
