import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TechSession as Session } from "@/lib/interview";
import { TechSession } from "./TechSession";

vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

function fakeStream(kind: "video" | "audio") {
  const track = { kind, readyState: "live", stop: vi.fn(function (this: { readyState: string }) { this.readyState = "ended"; }), addEventListener: vi.fn(), removeEventListener: vi.fn() };
  return { track, stream: { getTracks: () => [track], getVideoTracks: () => (kind === "video" ? [track] : []), getAudioTracks: () => (kind === "audio" ? [track] : []) } as unknown as MediaStream };
}

const session: Session = {
  id: 5, type: "tech", status: "in_progress", created_at: "2026-11-03T00:00:00Z", voice_enabled: true,
  role: "Backend Engineer", level: "mid", level_label: "Mid-level", mode: "practice", voice_only: false, proctored: true, focus: "",
  current_question: { position: 0, question: "Q?", category: "experience", category_label: "Experience", intro: null, is_follow_up: false, number: 1, total: 6, started: false, seconds_left: null },
  answered_main: 0, total_main: 6, turns: [], report: null, draft: null,
  integrity: { monitored: true, warnings: 0, status: "clean", events: {} },
};

describe("device check", () => {
  let camera: ReturnType<typeof fakeStream>, mic: ReturnType<typeof fakeStream>;
  let grantMic: () => void;

  beforeEach(() => {
    camera = fakeStream("video"); mic = fakeStream("audio");
    // Like a real browser, the microphone arrives a moment after the camera (the permission prompt),
    // so the page renders with the camera on before the mic exists.
    const micReady = new Promise<MediaStream>((resolve) => { grantMic = () => resolve(mic.stream); });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn((constraints: MediaStreamConstraints) => (constraints.video ? Promise.resolve(camera.stream) : micReady)) },
    });
    // The microphone level meter needs an AudioContext; jsdom has none.
    vi.stubGlobal("AudioContext", class {
      createAnalyser() { return { fftSize: 0, getFloatTimeDomainData: () => undefined }; }
      createMediaStreamSource() { return { connect: () => undefined }; }
      close() { return Promise.resolve(); }
    });
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("keeps the camera running after the microphone turns on", async () => {
    render(<TechSession session={session} refresh={async () => undefined} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /turn on camera & mic/i })); });
    await act(async () => { grantMic(); });
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledTimes(2);
    // Regression: the lobby's cleanup ran on every device change and stopped the camera when the mic arrived.
    expect(camera.track.stop).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /join interview/i })).toBeEnabled();
  });

  it("releases both devices when leaving the check without joining", async () => {
    const { unmount } = render(<TechSession session={session} refresh={async () => undefined} />);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /turn on camera & mic/i })); });
    await act(async () => { grantMic(); });
    unmount();
    expect(camera.track.stop).toHaveBeenCalled();
    expect(mic.track.stop).toHaveBeenCalled();
  });
});
