"use client";

import { useEffect, useRef, useState } from "react";
import type { FaceDetector } from "@mediapipe/tasks-vision";
import { api } from "@/lib/api";
import { assessFrame, type FaceIssue, IssueTracker } from "@/lib/proctor";

type Warning = FaceIssue | "tab_hidden";
type QueuedEvent = { kind: string; duration_ms: number; position: number | null };
export type ProctorState = { status: "off" | "loading" | "watching" | "error"; warning: Warning | null; warnings: number };

const FRAME_INTERVAL_MS = 250;
let detectorPromise: Promise<FaceDetector> | null = null;

function loadDetector() {
  detectorPromise ??= import("@mediapipe/tasks-vision").then(async ({ FaceDetector, FilesetResolver }) => {
    const fileset = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
    const create = (delegate: "GPU" | "CPU") => FaceDetector.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: "/mediapipe/blaze_face_short_range.tflite", delegate },
      runningMode: "VIDEO",
      minDetectionConfidence: 0.5,
    });
    // Machines without WebGL2 cannot use the GPU delegate; the CPU delegate is slower but fine at four frames a second.
    return create("GPU").catch(() => create("CPU"));
  }).catch((error) => { detectorPromise = null; throw error; });
  return detectorPromise;
}

/**
 * Watches the candidate's camera locally and reports sustained issues. Video frames never
 * leave the browser; only event types and durations are sent to the server.
 */
export function useProctor({ enabled, video, interviewId, position }: { enabled: boolean; video: HTMLVideoElement | null; interviewId: number; position: number | null }): ProctorState {
  const [state, setState] = useState<ProctorState>({ status: enabled ? "loading" : "off", warning: null, warnings: 0 });
  const positionRef = useRef(position);
  const queue = useRef<QueuedEvent[]>([]);
  useEffect(() => { positionRef.current = position; }, [position]);

  useEffect(() => {
    if (!enabled) return;
    const flush = () => {
      if (!queue.current.length) return;
      const events = queue.current.splice(0, 50);
      void api(`/interviews/${interviewId}/proctor-events`, { method: "POST", body: JSON.stringify({ events }), keepalive: true }).catch(() => undefined);
    };
    const timer = setInterval(flush, 5000);
    return () => { clearInterval(timer); flush(); };
  }, [enabled, interviewId]);

  useEffect(() => {
    if (!enabled) return;
    let hiddenSince: number | null = null;
    const record = (kind: string, durationMs: number) => {
      queue.current.push({ kind, duration_ms: Math.min(Math.max(0, durationMs), 3_600_000), position: positionRef.current });
      setState((current) => ({ ...current, warnings: current.warnings + 1 }));
    };
    const onVisibility = () => {
      if (document.hidden) { hiddenSince = performance.now(); setState((current) => ({ ...current, warning: "tab_hidden" })); }
      else if (hiddenSince != null) {
        record("tab_hidden", performance.now() - hiddenSince); hiddenSince = null;
        setState((current) => ({ ...current, warning: current.warning === "tab_hidden" ? null : current.warning }));
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [enabled]);

  useEffect(() => {
    if (!enabled || !video) return;
    let cancelled = false, frame = 0, lastRun = 0;
    const tracker = new IssueTracker();
    const record = (kind: string, durationMs: number) => {
      queue.current.push({ kind, duration_ms: durationMs, position: positionRef.current });
      setState((current) => ({ ...current, warnings: current.warnings + 1 }));
    };
    loadDetector().then((detector) => {
      if (cancelled) return;
      setState((current) => ({ ...current, status: "watching" }));
      const tick = (now: number) => {
        if (cancelled) return;
        frame = requestAnimationFrame(tick);
        if (now - lastRun < FRAME_INTERVAL_MS || video.readyState < 2 || document.hidden) return;
        lastRun = now;
        let issue: FaceIssue | null;
        try {
          const result = detector.detectForVideo(video, now);
          issue = assessFrame(result.detections.map((item) => ({ score: item.categories[0]?.score ?? 0, keypoints: item.keypoints })));
        } catch { return; }
        const finished = tracker.update(issue, now);
        if (finished) record(finished.kind, finished.durationMs);
        const active = tracker.active?.kind ?? null;
        setState((current) => current.warning === active || current.warning === "tab_hidden" ? current : { ...current, warning: active });
      };
      frame = requestAnimationFrame(tick);
    }).catch(() => { if (!cancelled) setState((current) => ({ ...current, status: "error" })); });
    return () => {
      cancelled = true; cancelAnimationFrame(frame);
      const finished = tracker.flush(performance.now());
      if (finished) record(finished.kind, finished.durationMs);
    };
  }, [enabled, video]);

  return enabled ? state : { status: "off", warning: null, warnings: 0 };
}
