"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { type CurrentQuestion, isPlaybackInterruption, type TurnResult } from "@/lib/interview";
import { EndOfSpeechDetector, preferredMimeType, questionAudioUrl, rms, transcribe } from "@/lib/voice";

export type CallPhase = "connecting" | "speaking" | "listening" | "thinking" | "ended";
type Options = {
  interviewId: number; question: CurrentQuestion | null; active: boolean; micStream: MediaStream | null;
  maxAnswerSeconds: number; onTurn: (result: TurnResult) => Promise<unknown>;
};

/** Hands-free interview loop: speak the question, listen, detect the end of the answer, submit, repeat. */
export function useVoiceCall({ interviewId, question, active, micStream, maxAnswerSeconds, onTurn }: Options) {
  const [phase, setPhase] = useState<CallPhase>("connecting");
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [notice, setNotice] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const loopRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const forcedRef = useRef(false);
  const onTurnRef = useRef(onTurn);
  useEffect(() => { onTurnRef.current = onTurn; }, [onTurn]);
  const position = question?.position ?? null;

  const stopLoop = useCallback(() => { if (loopRef.current) clearInterval(loopRef.current); loopRef.current = null; setLevel(0); }, []);

  const analyser = useCallback(() => {
    if (!micStream) return null;
    if (!contextRef.current) {
      const context = new AudioContext();
      const node = context.createAnalyser(); node.fftSize = 1024;
      context.createMediaStreamSource(micStream).connect(node);
      contextRef.current = context; analyserRef.current = node;
    }
    void contextRef.current.resume();
    return analyserRef.current;
  }, [micStream]);

  const submit = useCallback(async (answerPosition: number, answer: string, skip = false) => {
    setPhase("thinking");
    try {
      const result = await api<TurnResult>(`/interviews/${interviewId}/turns`, { method: "POST", body: JSON.stringify({ answer, skip, position: answerPosition }) });
      await onTurnRef.current(result);
      if (result.completed) setPhase("ended");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "Your answer could not be saved.");
      setPhase("listening");
    }
  }, [interviewId]);

  const listen = useCallback((answerPosition: number) => {
    const node = analyser();
    if (!micStream || !node) { setNotice("Your microphone isn't available."); return; }
    const mimeType = preferredMimeType();
    const recorder = new MediaRecorder(micStream, mimeType ? { mimeType } : undefined);
    const chunks: Blob[] = [];
    const detector = new EndOfSpeechDetector();
    const buffer = new Float32Array(node.fftSize);
    const started = performance.now();
    let timedOut = false;
    forcedRef.current = false;
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = async () => {
      stopLoop();
      if (timedOut && !detector.heardSpeech) { await submit(answerPosition, "", true); return; }
      if (!detector.heardSpeech && !forcedRef.current) return;
      const blob = new Blob(chunks, { type: (recorder.mimeType || mimeType || "audio/webm").split(";")[0] });
      setPhase("thinking");
      try {
        const text = blob.size ? await transcribe(interviewId, blob) : "";
        if (!text) { setNotice("I didn't catch that. Please answer again."); listen(answerPosition); return; }
        setNotice("");
        await submit(answerPosition, text);
      } catch (cause) {
        setNotice(cause instanceof Error ? cause.message : "We couldn't hear that clearly. Please try again.");
        listen(answerPosition);
      }
    };
    recorderRef.current = recorder;
    recorder.start(500);
    setPhase("listening"); setElapsed(0);
    loopRef.current = setInterval(() => {
      const now = performance.now();
      const value = rms(node, buffer);
      setLevel(Math.min(1, value * 8));
      setElapsed(Math.floor((now - started) / 1000));
      const timeUp = maxAnswerSeconds > 0 && now - started >= maxAnswerSeconds * 1000;
      if ((detector.push(value, now) || timeUp) && recorder.state === "recording") {
        forcedRef.current = timeUp;
        timedOut = timeUp;
        recorder.stop();
      }
    }, 100);
  }, [analyser, interviewId, maxAnswerSeconds, micStream, stopLoop, submit]);

  const speak = useCallback((questionPosition: number) => {
    audioRef.current?.pause();
    const audio = new Audio(questionAudioUrl(interviewId, questionPosition));
    audioRef.current = audio;
    setPhase("speaking");
    audio.onended = () => listen(questionPosition);
    audio.onerror = () => { setNotice("The interviewer's voice is unavailable right now."); listen(questionPosition); };
    audio.play().catch((cause) => {
      // Paused because the question changed or the call ended: the next question starts its own loop.
      if (isPlaybackInterruption(cause) || audioRef.current !== audio) return;
      setNotice("Tap “Repeat question” to hear the interviewer."); listen(questionPosition);
    });
  }, [interviewId, listen]);

  useEffect(() => {
    if (!active || position == null) return;
    // Starting audio playback here syncs the call with the newly loaded question.
    speak(position);
    return () => {
      audioRef.current?.pause();
      const recorder = recorderRef.current;
      if (recorder?.state === "recording") { recorder.onstop = null; recorder.stop(); }
      stopLoop();
    };
  }, [active, position, speak, stopLoop]);

  useEffect(() => () => { void contextRef.current?.close(); }, []);

  const finishAnswer = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") { forcedRef.current = true; recorder.stop(); }
  }, []);

  const repeat = useCallback(() => {
    if (position == null) return;
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") { recorder.onstop = null; recorder.stop(); }
    stopLoop(); setNotice(""); speak(position);
  }, [position, speak, stopLoop]);

  const skip = useCallback(() => {
    if (position == null) return;
    audioRef.current?.pause();
    const recorder = recorderRef.current;
    if (recorder?.state === "recording") { recorder.onstop = null; recorder.stop(); }
    stopLoop(); setNotice("");
    void submit(position, "", true);
  }, [position, stopLoop, submit]);

  return { phase, level, elapsed, notice, finishAnswer, repeat, skip };
}
