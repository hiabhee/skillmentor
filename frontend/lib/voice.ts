import { api } from "@/lib/api";

export function preferredMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

export async function transcribe(interviewId: number, blob: Blob) {
  const extension = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("audio", blob, `answer.${extension}`);
  const result = await api<{ transcript: string }>(`/interviews/${interviewId}/transcriptions`, { method: "POST", body: form });
  return result.transcript.trim();
}

export function questionAudioUrl(interviewId: number, position: number) {
  return `/api/v1/interviews/${interviewId}/questions/${position}/audio`;
}

/** Root-mean-square loudness of the current analyser frame, 0–1. */
export function rms(analyser: AnalyserNode, buffer: Float32Array<ArrayBuffer>) {
  analyser.getFloatTimeDomainData(buffer);
  let sum = 0;
  for (const value of buffer) sum += value * value;
  return Math.sqrt(sum / buffer.length);
}

/**
 * Decides when a spoken answer is finished: the candidate must speak for a moment,
 * then stay quiet for `silenceMs`. Thresholds adapt to the room's noise floor.
 */
export class EndOfSpeechDetector {
  private noiseFloor = 0.01;
  private speechMs = 0;
  private silenceStartedAt: number | null = null;
  private last: number | null = null;
  heardSpeech = false;

  constructor(private silenceMs = 2200, private minSpeechMs = 600) {}

  /** Feed one loudness sample; returns true when the answer looks complete. */
  push(level: number, now: number) {
    const delta = this.last == null ? 0 : Math.min(now - this.last, 250);
    this.last = now;
    const threshold = Math.max(0.02, this.noiseFloor * 2.5);
    if (level > threshold) {
      this.speechMs += delta;
      if (this.speechMs >= this.minSpeechMs) this.heardSpeech = true;
      this.silenceStartedAt = null;
      return false;
    }
    if (!this.heardSpeech) this.noiseFloor = this.noiseFloor * 0.95 + level * 0.05;
    if (!this.heardSpeech) return false;
    this.silenceStartedAt ??= now;
    return now - this.silenceStartedAt >= this.silenceMs;
  }
}
