"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { Loader2, Mic, Square, Volume2, VolumeX } from "lucide-react";
import { api } from "@/lib/api";
import { type InterviewOptions, isPlaybackInterruption, OPTIONS_PATH, type Preferences } from "@/lib/interview";
import { preferredMimeType, questionAudioUrl, transcribe } from "@/lib/voice";

const MAX_RECORDING_SECONDS = 180;

type Props = { interviewId: number; position: number; disabled: boolean; onTranscript: (text: string) => void };

export function VoiceControls({ interviewId, position, disabled, onTranscript }: Props) {
  // Auto-play is an account setting, so it follows the user across browsers and devices.
  const { data: options, mutate } = useSWR<InterviewOptions>(OPTIONS_PATH, (path: string) => api<InterviewOptions>(path));
  const autoplay = options?.preferences.autoplay ?? true;
  const autoplayed = useRef(false);
  const [speaking, setSpeaking] = useState(false);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const supported = typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";

  const stopSpeaking = useCallback(() => { audioRef.current?.pause(); setSpeaking(false); }, []);

  const speak = useCallback(async (quietOnBlock = false) => {
    stopSpeaking();
    const audio = new Audio(questionAudioUrl(interviewId, position));
    audioRef.current = audio;
    audio.onended = () => setSpeaking(false);
    audio.onerror = () => { setSpeaking(false); setError("The interviewer voice is unavailable. Read the question instead."); };
    try { setSpeaking(true); await audio.play(); }
    catch (cause) {
      if (audioRef.current === audio) setSpeaking(false);
      // Stopped on purpose (new question, Stop, leaving the page): not a failure.
      if (isPlaybackInterruption(cause)) return;
      // Browsers block autoplay before the first interaction; the play button stays available.
      if (!(quietOnBlock && cause instanceof DOMException && cause.name === "NotAllowedError")) setError("The question could not be played.");
    }
  }, [interviewId, position, stopSpeaking]);

  const releaseMic = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    // Read once per question (the component is keyed by position) after the saved setting loads; toggling never replays.
    if (!options || autoplayed.current) return;
    autoplayed.current = true;
    if (options.preferences.autoplay) void speak(true);
  }, [options, speak]);
  useEffect(() => () => audioRef.current?.pause(), []);

  useEffect(() => () => { if (recorderRef.current?.state === "recording") recorderRef.current.stop(); releaseMic(); }, [releaseMic]);

  async function toggleAutoplay() {
    if (!options) return;
    const loaded = options;
    const next = !autoplay;
    if (!next) stopSpeaking();
    // Show the change at once, then confirm with the server's saved value (or roll back on failure).
    await mutate(async (current) => {
      const saved = await api<{ preferences: Preferences }>("/preferences", { method: "PUT", body: JSON.stringify({ autoplay: next }) });
      return { ...(current ?? loaded), preferences: saved.preferences };
    }, { optimisticData: (current) => ({ ...(current ?? loaded), preferences: { ...(current ?? loaded).preferences, autoplay: next } }), rollbackOnError: true, revalidate: false })
      .catch(() => setError("Couldn't save the auto-play setting."));
  }

  async function upload(blob: Blob) {
    setTranscribing(true);
    try {
      const transcript = await transcribe(interviewId, blob);
      if (transcript) onTranscript(transcript); else setError("We didn't catch any speech. Try again a little closer to the mic.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "We couldn't transcribe that recording."); }
    finally { setTranscribing(false); }
  }

  async function startRecording() {
    setError(""); stopSpeaking();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      streamRef.current = stream;
      const mimeType = preferredMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        releaseMic(); setRecording(false);
        const blob = new Blob(chunks, { type: (recorder.mimeType || mimeType || "audio/webm").split(";")[0] });
        if (blob.size) void upload(blob);
      };
      recorderRef.current = recorder;
      recorder.start(1000);
      setElapsed(0); setRecording(true);
      timerRef.current = setInterval(() => setElapsed((seconds) => {
        if (seconds + 1 >= MAX_RECORDING_SECONDS && recorder.state === "recording") recorder.stop();
        return seconds + 1;
      }), 1000);
    } catch (cause) {
      releaseMic();
      setError(cause instanceof DOMException && cause.name === "NotAllowedError" ? "Microphone access was blocked. Allow it in your browser to answer by voice." : "Your microphone could not be started.");
    }
  }

  function stopRecording() { if (recorderRef.current?.state === "recording") recorderRef.current.stop(); }

  const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`;
  return <div className="voice-controls">
    <div className="voice-row">
      <button type="button" className="button quiet" onClick={() => (speaking ? stopSpeaking() : void speak())} disabled={recording}>{speaking ? <><Square size={13} />Stop</> : <><Volume2 size={14} />Hear question</>}</button>
      {supported && (recording
        ? <button type="button" className="button primary voice-recording" onClick={stopRecording}><Square size={13} />Stop · {clock}</button>
        : <button type="button" className="button secondary" onClick={() => void startRecording()} disabled={disabled || transcribing}>{transcribing ? <><Loader2 size={14} className="spin" />Transcribing…</> : <><Mic size={14} />Answer by voice</>}</button>)}
      <button type="button" className="voice-toggle" onClick={() => void toggleAutoplay()} disabled={!options} aria-pressed={autoplay}>{autoplay ? <Volume2 size={12} /> : <VolumeX size={12} />}{autoplay ? "Auto-play on" : "Auto-play off"}</button>
    </div>
    <p className="voice-hint">{supported ? `Speak your answer (up to ${MAX_RECORDING_SECONDS / 60} minutes). The transcript appears below so you can edit it before submitting.` : "Voice answers aren't supported in this browser. You can still listen to the question and type your answer."}</p>
    {error && <span className="inline-error" role="alert">{error}</span>}
  </div>;
}
