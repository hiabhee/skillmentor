"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";

export type DraftState = "idle" | "saving" | "saved" | "error";
const SAVE_DELAY_MS = 700;

/**
 * Text for the open question, autosaved to the server so a refresh, Leave, or another device loses nothing.
 * Key the component using this hook by question position; it starts from the server's saved draft.
 */
export function useDraft(interviewId: number, position: number | null, initial: string) {
  const [text, setTextState] = useState(initial);
  const [state, setState] = useState<DraftState>("idle");
  const textRef = useRef(initial);
  const unsaved = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flush = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (!unsaved.current || position === null) return;
    unsaved.current = false;
    setState("saving");
    try {
      // keepalive lets the save finish even when it was triggered by closing the tab.
      await api(`/interviews/${interviewId}/draft`, { method: "PUT", body: JSON.stringify({ position, text: textRef.current }), keepalive: true });
      setState("saved");
    } catch (cause) {
      // 409: the question was answered meanwhile (another tab or the submit itself); nothing left to save.
      setState(cause instanceof ApiError && cause.status === 409 ? "idle" : "error");
    }
  }, [interviewId, position]);

  const setText = useCallback((next: string | ((current: string) => string)) => {
    const value = typeof next === "function" ? next(textRef.current) : next;
    textRef.current = value;
    unsaved.current = true;
    setTextState(value);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => void flush(), SAVE_DELAY_MS);
  }, [flush]);

  /** Call after the answer is submitted: the server already deleted the draft. */
  const clear = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    unsaved.current = false;
    textRef.current = "";
    setTextState("");
    setState("idle");
  }, []);

  // Save what is pending when the question changes or the page is left inside the app.
  useEffect(() => () => { void flush(); }, [flush]);
  useEffect(() => {
    const onHide = () => { void flush(); };
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [flush]);

  return { text, setText, clear, state };
}

export function draftLabel(state: DraftState) {
  return state === "saving" ? "Saving draft…" : state === "saved" ? "Draft saved" : state === "error" ? "Draft not saved, check your connection" : "";
}
