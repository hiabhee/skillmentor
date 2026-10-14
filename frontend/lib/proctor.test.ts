import { describe, expect, it } from "vitest";
import { assessFrame, IssueTracker } from "@/lib/proctor";
import { EndOfSpeechDetector } from "@/lib/voice";

const face = (noseX = 0.5, score = 0.9) => ({ score, keypoints: [{ x: 0.45, y: 0.4 }, { x: 0.55, y: 0.4 }, { x: noseX, y: 0.47 }, { x: 0.5, y: 0.55 }] });

describe("face assessment", () => {
  it("accepts one centered face", () => expect(assessFrame([face()])).toBeNull());
  it("flags empty and crowded frames", () => {
    expect(assessFrame([])).toBe("no_face");
    expect(assessFrame([face(0.5, 0.3)])).toBe("no_face");
    expect(assessFrame([face(), face()])).toBe("multiple_faces");
  });
  it("flags a head turned away", () => expect(assessFrame([face(0.56)])).toBe("looking_away"));
});

describe("issue tracker", () => {
  it("ignores brief glances and reports sustained issues once resolved", () => {
    const tracker = new IssueTracker();
    expect(tracker.update("looking_away", 0)).toBeNull();
    expect(tracker.update(null, 1000)).toBeNull();
    expect(tracker.active).toBeNull();
    tracker.update("no_face", 2000);
    tracker.update("no_face", 3600);
    expect(tracker.active?.kind).toBe("no_face");
    expect(tracker.update(null, 6000)).toEqual({ kind: "no_face", durationMs: 4000 });
  });
});

describe("end of speech", () => {
  it("waits for speech, then a sustained pause", () => {
    const detector = new EndOfSpeechDetector(2000, 400);
    let t = 0;
    for (; t < 3000; t += 100) expect(detector.push(0.005, t)).toBe(false);
    for (; t < 4000; t += 100) expect(detector.push(0.2, t)).toBe(false);
    expect(detector.heardSpeech).toBe(true);
    let done = false;
    for (; t < 7000 && !done; t += 100) done = detector.push(0.004, t);
    expect(done).toBe(true);
    expect(t).toBeGreaterThanOrEqual(6000);
  });
});
