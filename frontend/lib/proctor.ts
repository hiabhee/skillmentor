export type FaceIssue = "no_face" | "multiple_faces" | "looking_away";
type Point = { x: number; y: number };
export type FaceObservation = { keypoints: Point[]; score: number };

/**
 * Classify one frame from MediaPipe's short-range face detector. Keypoints are
 * normalized: right eye, left eye, nose tip, mouth, right ear, left ear.
 */
export function assessFrame(faces: FaceObservation[], minScore = 0.6): FaceIssue | null {
  const confident = faces.filter((face) => face.score >= minScore);
  if (confident.length === 0) return "no_face";
  if (confident.length > 1) return "multiple_faces";
  const [rightEye, leftEye, nose, mouth] = confident[0].keypoints;
  if (!rightEye || !leftEye || !nose || !mouth) return null;
  const eyeSpan = Math.hypot(leftEye.x - rightEye.x, leftEye.y - rightEye.y);
  if (eyeSpan < 0.02) return "looking_away";
  // Turning the head moves the nose toward one eye; tilting it moves the nose toward the eyes or mouth.
  const yaw = (nose.x - (leftEye.x + rightEye.x) / 2) / eyeSpan;
  const eyeY = (leftEye.y + rightEye.y) / 2;
  const pitch = (nose.y - eyeY) / Math.max(mouth.y - eyeY, 1e-3);
  if (Math.abs(yaw) > 0.42 || pitch < 0.25 || pitch > 0.95) return "looking_away";
  const cx = nose.x;
  if (cx < 0.08 || cx > 0.92) return "looking_away";
  return null;
}

/** How long an issue must persist before it becomes a warning, so a blink or quick glance never counts. */
export const ISSUE_GRACE_MS: Record<FaceIssue, number> = { no_face: 1500, multiple_faces: 1000, looking_away: 3000 };

export const ISSUE_COPY: Record<FaceIssue | "tab_hidden", { title: string; detail: string }> = {
  no_face: { title: "We can't see you", detail: "Move back into the camera frame." },
  multiple_faces: { title: "Someone else is in view", detail: "Interviews must be taken alone." },
  looking_away: { title: "Eyes on the interview", detail: "Look back toward your screen." },
  tab_hidden: { title: "You left the interview tab", detail: "Stay on this tab until the interview ends." },
};

/** Tracks one issue at a time and reports a completed event once it resolves. */
export class IssueTracker {
  private candidate: { kind: FaceIssue; since: number } | null = null;
  active: { kind: FaceIssue; since: number } | null = null;

  update(issue: FaceIssue | null, now: number): { kind: FaceIssue; durationMs: number } | null {
    let finished: { kind: FaceIssue; durationMs: number } | null = null;
    if (this.active && this.active.kind !== issue) {
      finished = { kind: this.active.kind, durationMs: Math.round(now - this.active.since) };
      this.active = null;
    }
    if (!issue) { this.candidate = null; return finished; }
    if (this.active) return finished;
    if (!this.candidate || this.candidate.kind !== issue) this.candidate = { kind: issue, since: now };
    if (now - this.candidate.since >= ISSUE_GRACE_MS[issue]) { this.active = this.candidate; this.candidate = null; }
    return finished;
  }

  flush(now: number) {
    const finished = this.active ? { kind: this.active.kind, durationMs: Math.round(now - this.active.since) } : null;
    this.active = null; this.candidate = null;
    return finished;
  }
}
