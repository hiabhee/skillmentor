"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, AudioLines, Check, CircleAlert, Headphones, Keyboard, Lightbulb, Loader2, Mic, PhoneOff, RotateCcw, ScanFace, ShieldCheck, SkipForward, Timer, Video } from "lucide-react";
import { api } from "@/lib/api";
import { draftLabel, useDraft } from "@/lib/draft";
import { type Feedback, type TechSession as Session, type Turn, type TurnResult } from "@/lib/interview";
import { ISSUE_COPY } from "@/lib/proctor";
import { VoiceControls } from "@/components/VoiceControls";
import { InterviewerOrb } from "./InterviewerOrb";
import { TechReport } from "./TechReport";
import { useProctor } from "./useProctor";
import { type CallPhase, useVoiceCall } from "./useVoiceCall";

type Devices = { camera: MediaStream | null; mic: MediaStream | null };

export function TechSession({ session, refresh }: { session: Session; refresh: () => Promise<unknown> }) {
  const [devices, setDevices] = useState<Devices | null>(null);
  useEffect(() => () => { devices?.camera?.getTracks().forEach((track) => track.stop()); devices?.mic?.getTracks().forEach((track) => track.stop()); }, [devices]);
  if (session.status === "completed") return <TechReport session={session} refresh={refresh} />;
  if (!devices) return <Lobby session={session} refresh={refresh} onJoin={setDevices} />;
  return <LiveRoom session={session} devices={devices} refresh={refresh} />;
}

const openCamera = () => navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
const cameraLive = (stream: MediaStream | null) => stream?.getVideoTracks()[0]?.readyState === "live";

function SessionTags({ session }: { session: Session }) {
  return <div className="tech-tags"><span className={`mode-pill ${session.mode}`}>{session.mode === "assessment" ? "Assessment" : "Practice"}</span><span>{session.level_label}</span><span>{session.voice_only ? "Voice call" : "Voice + text"}</span>{session.proctored && <span><ScanFace size={12} />Camera on</span>}</div>;
}

function Lobby({ session, refresh, onJoin }: { session: Session; refresh: () => Promise<unknown>; onJoin: (devices: Devices) => void }) {
  const needsMic = session.voice_only;
  const wantsMic = session.voice_enabled;
  const [camera, setCamera] = useState<MediaStream | null>(null);
  const [mic, setMic] = useState<MediaStream | null>(null);
  const [error, setError] = useState("");
  const [level, setLevel] = useState(0);
  const [joining, setJoining] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const handedOff = useRef(false);
  const held = useRef<Devices>({ camera: null, mic: null });

  useEffect(() => { if (videoRef.current && camera) videoRef.current.srcObject = camera; }, [camera]);
  useEffect(() => {
    if (!mic) return;
    const context = new AudioContext(); const analyser = context.createAnalyser(); analyser.fftSize = 512;
    context.createMediaStreamSource(mic).connect(analyser);
    const buffer = new Float32Array(analyser.fftSize);
    const timer = setInterval(() => { analyser.getFloatTimeDomainData(buffer); let sum = 0; for (const v of buffer) sum += v * v; setLevel(Math.min(1, Math.sqrt(sum / buffer.length) * 10)); }, 80);
    return () => { clearInterval(timer); void context.close(); };
  }, [mic]);
  // Release devices only when the lobby closes without joining. Tying this to [camera, mic] stopped the
  // camera the moment the microphone turned on, so the live room got a black, untrackable feed.
  useEffect(() => {
    const streams = held.current;
    return () => { if (!handedOff.current) { streams.camera?.getTracks().forEach((t) => t.stop()); streams.mic?.getTracks().forEach((t) => t.stop()); } };
  }, []);

  async function enable() {
    setError("");
    try {
      if (session.proctored && !cameraLive(camera)) { const stream = await openCamera(); held.current.camera = stream; setCamera(stream); }
      if (wantsMic && !mic) { const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); held.current.mic = stream; setMic(stream); }
    } catch (cause) {
      setError(cause instanceof DOMException && cause.name === "NotAllowedError" ? "Permission was blocked. Allow camera and microphone in your browser's address bar, then try again." : "We couldn't start your devices. Check that no other app is using them.");
    }
  }

  const ready = (!session.proctored || cameraLive(camera)) && (!needsMic || mic);

  async function join() {
    setJoining(true); setError("");
    try {
      // The server starts the answer clock here, once; a reload or rejoin continues it instead of resetting it.
      await api(`/interviews/${session.id}/join`, { method: "POST" });
      await refresh();
      handedOff.current = true; onJoin({ camera, mic });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "We couldn't join the interview."); setJoining(false); }
  }
  const q = session.current_question;
  const resuming = (q?.position ?? 0) > 0;
  return <div className="lobby">
    <Link className="back-link" href="/practice"><ArrowLeft size={15} /> Practice</Link>
    <div className="lobby-grid">
      <section className="lobby-preview">
        <div className={`preview-frame ${camera ? "live" : ""}`}>
          {camera ? <video ref={videoRef} autoPlay playsInline muted /> : <div className="preview-empty"><InterviewerOrb phase="connecting" level={0} size="large" /><span>{session.proctored ? "Your camera preview appears here" : "Camera is off for this session"}</span></div>}
          {wantsMic && <div className="mic-meter" aria-label="Microphone level"><Mic size={13} />{Array.from({ length: 12 }, (_, i) => <i key={i} className={level * 12 > i ? "on" : ""} />)}</div>}
        </div>
        <ul className="device-checks">
          {session.proctored && <li className={camera ? "ok" : ""}>{camera ? <Check size={14} /> : <Video size={14} />}Camera {camera ? "ready" : "needed for face tracking"}</li>}
          {wantsMic && <li className={mic ? "ok" : ""}>{mic ? <Check size={14} /> : <Mic size={14} />}Microphone {mic ? (level > 0.15 ? "hears you" : "ready, say something") : needsMic ? "needed" : "optional"}</li>}
          <li className="ok"><Headphones size={14} />Headphones recommended so the mic doesn&apos;t hear the interviewer</li>
        </ul>
      </section>
      <section className="lobby-copy">
        <span className="eyebrow">{resuming ? "WELCOME BACK" : "YOU'RE UP NEXT"}</span>
        <h1>{session.role}</h1>
        <SessionTags session={session} />
        <p className="lobby-lede">{session.voice_only ? "This is a hands-free voice call. Alex asks each question out loud, listens while you answer, and moves on when you pause." : "Alex reads each question aloud. Answer by voice or by typing, then submit."}{session.mode === "assessment" ? " Scores stay hidden until you finish." : " You'll get coaching after every answer."}</p>
        <ol className="lobby-rules">
          <li><span>{session.total_main}</span>questions{resuming ? `, resuming at question ${q?.number ?? 1}` : ""}</li>
          {q?.seconds_left != null && <li><Timer size={14} />{q.started ? `${clock(q.seconds_left)} left on this answer` : `${Math.round(q.seconds_left / 60)} minutes per answer`}</li>}
          {session.proctored && <li><ShieldCheck size={14} />Face tracking runs only in your browser. Video is never uploaded.</li>}
          {session.voice_only && <li><AudioLines size={14} />Pause for about two seconds when you finish an answer</li>}
        </ol>
        {error && <div className="notice error-notice">{error}</div>}
        <div className="lobby-actions">
          {!ready || (wantsMic && !mic) ? <button className="button secondary" onClick={() => void enable()}><Video size={15} />Turn on {session.proctored ? (wantsMic ? "camera & mic" : "camera") : "microphone"}</button> : null}
          <button className="button primary join-button" disabled={!ready || joining} onClick={() => void join()}>{joining ? <><Loader2 size={15} className="spin" />Joining…</> : <>{resuming ? "Rejoin interview" : "Join interview"}<ArrowRight size={16} /></>}</button>
        </div>
      </section>
    </div>
  </div>;
}

/** Counts down from the server's remaining time; each refetch re-syncs it, so a reload never adds time. */
function useCountdown(key: number | null, seconds: number | null, onExpire: () => void) {
  const [left, setLeft] = useState(seconds ?? 0);
  const expire = useRef(onExpire);
  useEffect(() => { expire.current = onExpire; }, [onExpire]);
  useEffect(() => {
    if (seconds == null || key == null) return;
    const deadline = Date.now() + seconds * 1000;
    const timer = setInterval(() => {
      const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setLeft(remaining);
      if (remaining === 0) { clearInterval(timer); expire.current(); }
    }, 500);
    return () => { clearInterval(timer); setLeft(seconds ?? 0); };
  }, [key, seconds]);
  return left;
}

const clock = (value: number) => `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
const PHASE_LABEL: Record<CallPhase, string> = { connecting: "Connecting…", speaking: "Alex is speaking", listening: "Listening to you", thinking: "Alex is thinking", ended: "Interview complete" };

function LiveRoom({ session, devices, refresh }: { session: Session; devices: Devices; refresh: () => Promise<unknown> }) {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null);
  const [camera, setCamera] = useState<MediaStream | null>(devices.camera);
  // When the camera stopped (unplugged, permission revoked, another app took it); null while it is live.
  const [cameraLostAt, setCameraLostAt] = useState<number | null>(() => devices.camera && !cameraLive(devices.camera) ? Date.now() : null);
  const [cameraError, setCameraError] = useState("");
  const restarted = useRef<MediaStream | null>(null);
  const lostAtRef = useRef(cameraLostAt);
  useEffect(() => { lostAtRef.current = cameraLostAt; }, [cameraLostAt]);
  const question = session.current_question;
  const positionRef = useRef(question?.position ?? null);
  useEffect(() => { positionRef.current = question?.position ?? null; }, [question?.position]);
  const last = lastFeedback(session);
  // A stopped camera is a device problem, not "no face": pause face tracking instead of logging false warnings.
  const proctor = useProctor({ enabled: session.proctored && !!camera && cameraLostAt === null, video, interviewId: session.id, position: question?.position ?? null });
  useEffect(() => { if (video && camera) video.srcObject = camera; }, [video, camera]);
  useEffect(() => {
    const track = camera?.getVideoTracks()[0];
    if (!track) return;
    const onEnded = () => setCameraLostAt((current) => current ?? Date.now());
    track.addEventListener("ended", onEnded);
    return () => track.removeEventListener("ended", onEnded);
  }, [camera]);

  const reportCameraOff = useCallback((lostAt: number) => {
    const events = [{ kind: "camera_off", duration_ms: Math.min(Date.now() - lostAt, 3_600_000), position: positionRef.current }];
    void api(`/interviews/${session.id}/proctor-events`, { method: "POST", body: JSON.stringify({ events }), keepalive: true }).catch(() => undefined);
  }, [session.id]);
  useEffect(() => () => {
    restarted.current?.getTracks().forEach((track) => track.stop());
    if (lostAtRef.current !== null) reportCameraOff(lostAtRef.current);
  }, [reportCameraOff]);

  async function restartCamera() {
    setCameraError("");
    try {
      const stream = await openCamera();
      restarted.current?.getTracks().forEach((track) => track.stop());
      restarted.current = stream;
      if (cameraLostAt !== null) reportCameraOff(cameraLostAt);
      setCamera(stream); setCameraLostAt(null);
    } catch (cause) {
      setCameraError(cause instanceof DOMException && cause.name === "NotAllowedError" ? "Camera permission is blocked. Allow it in the address bar." : "The camera is busy or unavailable.");
    }
  }

  const onTurn = useCallback(async () => { await refresh(); }, [refresh]);

  const progress = session.total_main ? ((question ? question.number - 1 : session.total_main) / session.total_main) * 100 : 0;
  const warning = cameraLostAt !== null ? { title: "Your camera stopped", detail: "Turn it back on to continue face tracking. The time it was off is noted in your integrity report." }
    : proctor.warning ? ISSUE_COPY[proctor.warning] : null;
  return <div className={`live-room ${warning ? "has-warning" : ""}`}>
    <header className="live-top">
      <div className="live-title"><span className="live-dot" />LIVE<strong>{session.role}</strong><SessionTags session={session} /></div>
      <div className="live-progress"><span>Question {question?.number ?? session.total_main} of {session.total_main}{question?.is_follow_up ? " · follow-up" : ""}</span><div className="progress-track"><div style={{ width: `${progress}%` }} /></div></div>
      <Link className="button quiet leave-button" href="/practice" title="Your progress is saved. You can rejoin from your dashboard."><PhoneOff size={15} />Leave</Link>
    </header>
    {warning && <div className="proctor-toast" role="alert"><CircleAlert size={18} /><div><strong>{warning.title}</strong><span>{warning.detail}</span></div></div>}
    <div className="live-grid">
      {session.voice_only
        ? <VoiceStage session={session} mic={devices.mic} onTurn={onTurn} />
        : <TextStage key={question?.position ?? -1} session={session} onTurn={onTurn} last={last} />}
      <aside className="live-side">
        {session.proctored && <div className={`self-view ${proctor.warning || cameraLostAt !== null ? "warn" : ""}`}><video ref={setVideo} autoPlay playsInline muted />{cameraLostAt !== null
          ? <div className="camera-lost"><span><Video size={14} />Camera stopped</span><button type="button" className="button secondary" onClick={() => void restartCamera()}>Turn camera back on</button>{cameraError && <small>{cameraError}</small>}</div>
          : <span className={`face-pill ${proctor.status}`}>{proctor.status === "watching" ? (proctor.warning ? <><CircleAlert size={12} />Check position</> : <><ScanFace size={12} />Face tracked</>) : proctor.status === "error" ? "Tracking unavailable" : <><Loader2 size={12} className="spin" />Starting tracking</>}</span>}</div>}
        <div className="panel live-panel">
          <span className="eyebrow">THIS QUESTION</span>
          <h3>{question?.category_label ?? "Wrapping up"}</h3>
          <div className="question-dots">{Array.from({ length: session.total_main }, (_, i) => <i key={i} className={i < (question ? question.number - 1 : session.total_main) ? "done" : question && i === question.number - 1 ? "current" : ""} />)}</div>
          {session.proctored && <p className="integrity-line"><ShieldCheck size={13} />{proctor.warnings === 0 ? "No integrity warnings" : `${proctor.warnings} integrity ${proctor.warnings === 1 ? "warning" : "warnings"} logged`}</p>}
          {session.mode === "practice" && !session.voice_only && <div className="tip-note"><Lightbulb size={13} /><span>Name the trade-off. Interviewers listen for <em>why</em>, not just <em>what</em>.</span></div>}
        </div>
      </aside>
    </div>
  </div>;
}

function VoiceStage({ session, mic, onTurn }: { session: Session; mic: MediaStream | null; onTurn: (result: TurnResult) => Promise<unknown> }) {
  const question = session.current_question;
  const maxSeconds = question?.seconds_left ?? 300;
  const call = useVoiceCall({ interviewId: session.id, question, active: true, micStream: mic, maxAnswerSeconds: maxSeconds, onTurn });
  return <section className="stage voice-stage">
    <div className="stage-glow" />
    <InterviewerOrb phase={call.phase} level={call.level} size="hero" />
    <div className="stage-name"><strong>Alex</strong><span>AI interviewer · {session.role}</span></div>
    <div className={`phase-chip ${call.phase}`}>{call.phase === "listening" ? <Mic size={14} /> : call.phase === "thinking" ? <Loader2 size={14} className="spin" /> : <AudioLines size={14} />}{PHASE_LABEL[call.phase]}{call.phase === "listening" && <b>{clock(call.elapsed)}{session.mode === "assessment" ? ` / ${clock(maxSeconds)}` : ""}</b>}</div>
    {call.notice && <p className="stage-notice">{call.notice}</p>}
    <div className="call-controls">
      <button className="call-button" onClick={call.repeat} disabled={call.phase === "thinking"}><RotateCcw size={18} /><span>Repeat</span></button>
      <button className="call-button primary" onClick={call.finishAnswer} disabled={call.phase !== "listening"}><Check size={20} /><span>I&apos;m done</span></button>
      <button className="call-button" onClick={call.skip} disabled={call.phase === "thinking"}><SkipForward size={18} /><span>Skip</span></button>
    </div>
    <p className="stage-hint">Answer naturally. When you pause for about two seconds, Alex moves on. Tap <b>I&apos;m done</b> to move on sooner.</p>
  </section>;
}

type LastFeedbackData = { question: string; feedback: Feedback };

/** Feedback on the most recent answer, from the server's saved turns so it survives a reload. */
function lastFeedback(session: Session): LastFeedbackData | null {
  const turn: Turn | undefined = session.turns[session.turns.length - 1];
  if (!turn?.feedback || session.mode !== "practice") return null;
  try { return { question: turn.question, feedback: JSON.parse(turn.feedback) as Feedback }; } catch { return null; }
}

function TextStage({ session, onTurn, last }: { session: Session; onTurn: (result: TurnResult) => Promise<unknown>; last: LastFeedbackData | null }) {
  const question = session.current_question;
  const position = question?.position ?? null;
  const draft = useDraft(session.id, position, session.draft && session.draft.position === position ? session.draft.text : "");
  const { text: answer, setText: setAnswer, clear: clearDraft } = draft;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const answerRef = useRef(answer);
  useEffect(() => { answerRef.current = answer; }, [answer]);

  const submit = useCallback(async (skip: boolean) => {
    if (!question) return;
    const text = answerRef.current.trim();
    setPending(true); setError("");
    try {
      const result = await api<TurnResult>(`/interviews/${session.id}/turns`, { method: "POST", body: JSON.stringify({ answer: skip ? "" : text, skip: skip || !text, position: question.position }) });
      clearDraft(); await onTurn(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Your answer could not be saved."); }
    finally { setPending(false); }
  }, [clearDraft, onTurn, question, session.id]);

  const seconds = question?.seconds_left ?? null;
  const left = useCountdown(position, seconds, () => void submit(false));
  if (!question) return <section className="stage"><Loader2 className="spin" /> Wrapping up…</section>;
  function handleSubmit(event: FormEvent) { event.preventDefault(); void submit(false); }
  return <section className="stage text-stage">
    {last && <LastFeedback last={last} />}
    <div className="interviewer-line">
      <InterviewerOrb phase={pending ? "thinking" : "speaking"} level={0} size="small" />
      <div><span className="eyebrow">ALEX · {question.category_label.toUpperCase()}{question.is_follow_up ? " · FOLLOW-UP" : ""}</span>{question.intro && <p className="interviewer-intro">{question.intro}</p>}<h2>{question.question}</h2></div>
      {seconds != null && <span className={`countdown ${left <= 30 ? "urgent" : ""}`}><Timer size={14} />{clock(left)}</span>}
    </div>
    {session.voice_enabled && <VoiceControls key={question.position} interviewId={session.id} position={question.position} disabled={pending} onTranscript={(text) => setAnswer((current) => (current.trim() ? `${current.trim()} ${text}` : text).slice(0, 20000))} />}
    <form onSubmit={handleSubmit} className="answer-form">
      <label className="field-label" htmlFor="answer"><span><Keyboard size={12} /> Your answer</span></label>
      <textarea id="answer" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Think out loud: approach, trade-offs, and an example from your experience…" maxLength={20000} rows={7} disabled={pending} />
      <div className="answer-tools"><span>{answer.length.toLocaleString()} / 20,000{draftLabel(draft.state) && <> · <span className={draft.state === "error" ? "inline-error" : ""}>{draftLabel(draft.state)}</span></>}</span><div>{error && <span className="inline-error">{error}</span>}<button type="button" className="button quiet" onClick={() => void submit(true)} disabled={pending}>Skip</button><button className="button primary" disabled={pending || !answer.trim()}>{pending ? <><Loader2 size={14} className="spin" />Alex is reviewing…</> : <>Submit answer<ArrowRight size={15} /></>}</button></div></div>
    </form>
  </section>;
}

function LastFeedback({ last }: { last: LastFeedbackData }) {
  const feedback = last.feedback;
  return <details className="last-feedback" open>
    <summary><span className={`score-chip tone-${(feedback.score ?? 0) >= 8 ? "strong" : (feedback.score ?? 0) >= 6 ? "good" : "fair"}`}>{feedback.score ?? "—"}<small>/10</small></span><span><strong>Feedback on your last answer</strong><small>{last.question}</small></span></summary>
    <div className="last-feedback-body">
      {feedback.strengths?.length ? <div><strong>Worked well</strong>{feedback.strengths.map((item) => <p key={item}><Check size={13} />{item}</p>)}</div> : null}
      {feedback.improvements?.length ? <div><strong>Level up</strong>{feedback.improvements.map((item) => <p key={item}><ArrowRight size={13} />{item}</p>)}</div> : null}
      {feedback.model_answer?.length ? <div className="model-answer"><strong>A strong answer covers</strong>{feedback.model_answer.map((item) => <p key={item}><Lightbulb size={13} />{item}</p>)}</div> : null}
    </div>
  </details>;
}
