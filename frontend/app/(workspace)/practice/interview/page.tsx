"use client";

import { Suspense, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR, { mutate } from "swr";
import { ArrowRight, AudioLines, BrainCircuit, Check, ClipboardCheck, Cloud, Database, GraduationCap, Keyboard, Layers, Loader2, Monitor, PenLine, ScanFace, Server, ShieldCheck, Smartphone, Sparkles, Timer } from "lucide-react";
import { api } from "@/lib/api";
import { type InterviewOptions, type Level, LEVELS, type Mode, OPTIONS_PATH, type Preferences, type RoleKey, ROLES } from "@/lib/interview";

const ROLE_ICONS: Record<RoleKey, typeof Monitor> = { frontend: Monitor, backend: Server, fullstack: Layers, mobile: Smartphone, data: Database, ml: BrainCircuit, devops: Cloud, security: ShieldCheck, custom: PenLine };

export default function InterviewSetupPage() {
  return <Suspense fallback={<div className="centered-state">Loading…</div>}><InterviewSetup /></Suspense>;
}

/** A link such as /practice/interview?role=frontend picks the role; otherwise the saved choice is used. */
function roleFromLink(param: string | null, saved: Preferences): { key: RoleKey; custom: string } {
  if (!param) return { key: saved.role, custom: saved.custom_role };
  const match = ROLES.find((role) => role.key === param || role.full.toLowerCase() === param.toLowerCase());
  return match ? { key: match.key, custom: "" } : { key: "custom", custom: param.slice(0, 60) };
}

function InterviewSetup() {
  const { data, error } = useSWR<InterviewOptions>(OPTIONS_PATH, (path: string) => api<InterviewOptions>(path), { revalidateOnFocus: false });
  if (error) return <div className="centered-state"><h2>Setup unavailable</h2><p>We couldn&apos;t load your interview options. Refresh the page to try again.</p></div>;
  if (!data) return <div className="centered-state">Loading your saved setup…</div>;
  return <SetupForm options={data} />;
}

function SetupForm({ options }: { options: InterviewOptions }) {
  const params = useSearchParams();
  const router = useRouter();
  const saved = options.preferences;
  const linked = roleFromLink(params.get("role"), saved);
  const linkedMode = params.get("mode");
  const [role, setRole] = useState<RoleKey>(linked.key);
  const [customRole, setCustomRole] = useState(linked.custom);
  const [level, setLevel] = useState<Level>(saved.level);
  // Saved focus areas only apply to the saved role; each role has its own topic list.
  const [focus, setFocus] = useState<string[]>(linked.key === saved.role ? saved.focus : []);
  const [mode, setMode] = useState<Mode>(linkedMode === "assessment" || linkedMode === "practice" ? linkedMode : saved.mode);
  const [voiceOnly, setVoiceOnly] = useState(saved.voice_only);
  const [camera, setCamera] = useState(saved.camera);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [saveNote, setSaveNote] = useState("");
  const queued = useRef<Partial<Preferences>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Save choices to the account as they change, so they come back on any device. */
  function remember(patch: Partial<Preferences>) {
    queued.current = { ...queued.current, ...patch };
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const body = queued.current; queued.current = {};
      api<{ preferences: Preferences }>("/preferences", { method: "PUT", body: JSON.stringify(body) })
        .then((result) => {
          // Keep the cached copy in step with the server so returning to this page shows these choices.
          void mutate<InterviewOptions>(OPTIONS_PATH, (current) => current && { ...current, preferences: result.preferences }, { revalidate: false });
          setSaveNote("Choices saved to your account");
        })
        .catch(() => setSaveNote("Couldn't save your choices. They'll be saved when you start."));
    }, 600);
  }

  const roleInfo = ROLES.find((item) => item.key === role)!;
  const rules = options.modes[mode];
  const voiceAvailable = options.voice_available;
  const useVoiceOnly = voiceAvailable && voiceOnly;
  const proctored = rules.camera_required || camera;
  const roleTitle = role === "custom" ? customRole.trim() || "Your role" : roleInfo.full;
  const practice = options.modes.practice, assessment = options.modes.assessment;

  function chooseRole(key: RoleKey) { setRole(key); setFocus([]); remember({ role: key, focus: [] }); }
  function chooseLevel(key: Level) { setLevel(key); remember({ level: key }); }
  function chooseMode(key: Mode) { setMode(key); remember({ mode: key }); }
  function chooseVoice(value: boolean) { setVoiceOnly(value); remember({ voice_only: value }); }
  function chooseCamera(value: boolean) { setCamera(value); remember({ camera: value }); }
  function typeCustomRole(value: string) { setCustomRole(value); remember({ custom_role: value.slice(0, 60) }); }
  function toggleFocus(item: string) {
    const next = focus.includes(item) ? focus.filter((value) => value !== item) : focus.length >= options.max_focus ? focus : [...focus, item];
    setFocus(next); remember({ focus: next });
  }

  async function begin() {
    if (role === "custom" && customRole.trim().length < 2) { setError("Type the role you're interviewing for."); return; }
    setPending(true); setError("");
    try {
      const result = await api<{ interview: { id: number } }>("/interviews", { method: "POST", body: JSON.stringify({ type: "tech", role, custom_role: customRole.trim(), level, mode, focus: focus.join(", "), voice_only: useVoiceOnly, proctored }) });
      // Starting saves these choices on the server; refresh the cached copy for the next visit.
      if (timer.current) clearTimeout(timer.current);
      void mutate(OPTIONS_PATH);
      router.push(`/sessions/${result.interview.id}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start your interview."); setPending(false); }
  }

  return <div className="setup">
    <div className="page-heading"><div><span className="eyebrow">BUILD YOUR INTERVIEW</span><h1>What role are you going after?</h1><p>Alex, your AI interviewer, tailors every question to the role, level and topics you choose.</p></div></div>
    <div className="setup-grid">
      <div className="setup-steps">
        <section className="setup-step"><div className="step-label"><span>1</span>Role</div>
          <div className="role-grid">{ROLES.map((item) => { const Icon = ROLE_ICONS[item.key]; return <button type="button" key={item.key} className={`role-card ${role === item.key ? "selected" : ""}`} onClick={() => chooseRole(item.key)} aria-pressed={role === item.key}><span className="role-icon"><Icon size={19} /></span><strong>{item.title}</strong><small>{item.blurb}</small>{role === item.key && <span className="role-check"><Check size={12} /></span>}</button>; })}</div>
          {role === "custom" && <input className="text-input" value={customRole} onChange={(event) => typeCustomRole(event.target.value)} maxLength={60} placeholder="e.g. Platform Engineer, Game Developer, QA Automation" autoFocus />}
        </section>
        <section className="setup-step"><div className="step-label"><span>2</span>Level</div>
          <div className="segmented">{LEVELS.map((item) => <button type="button" key={item.key} className={level === item.key ? "selected" : ""} onClick={() => chooseLevel(item.key)} aria-pressed={level === item.key}><strong>{item.title}</strong><small>{item.years}</small></button>)}</div>
        </section>
        <section className="setup-step"><div className="step-label"><span>3</span>Focus areas <em>optional · up to {options.max_focus}</em></div>
          <div className="chip-row">{roleInfo.focus.map((item) => <button type="button" key={item} className={`chip ${focus.includes(item) ? "selected" : ""}`} onClick={() => toggleFocus(item)} aria-pressed={focus.includes(item)}>{focus.includes(item) && <Check size={12} />}{item}</button>)}</div>
        </section>
        <section className="setup-step"><div className="step-label"><span>4</span>Session type</div>
          <div className="mode-grid">
            <button type="button" className={`mode-card ${mode === "practice" ? "selected" : ""}`} onClick={() => chooseMode("practice")} aria-pressed={mode === "practice"}><GraduationCap size={22} /><strong>Practice</strong><span>Coaching after every answer, model answers, no clock. Learn as you go.</span><ul><li><Check size={12} />{practice.questions} questions</li><li><Check size={12} />Instant feedback</li><li><Check size={12} />Camera optional</li></ul></button>
            <button type="button" className={`mode-card assessment ${mode === "assessment" ? "selected" : ""}`} onClick={() => chooseMode("assessment")} aria-pressed={mode === "assessment"}><ClipboardCheck size={22} /><strong>Assessment</strong><span>Real interview conditions. Timed answers, results only at the end, and a hire verdict.</span><ul><li><Timer size={12} />{assessment.questions} questions · {Math.round(assessment.answer_seconds / 60)} min each</li><li><ScanFace size={12} />Face tracking on</li><li><Sparkles size={12} />Scorecard & verdict</li></ul></button>
          </div>
        </section>
        <section className="setup-step"><div className="step-label"><span>5</span>Format</div>
          <div className="format-row">
            <button type="button" className={`format-card ${useVoiceOnly ? "selected" : ""}`} onClick={() => chooseVoice(true)} disabled={!voiceAvailable} aria-pressed={useVoiceOnly}><AudioLines size={18} /><span><strong>Voice call</strong><small>{voiceAvailable ? "Hands-free and spoken only, like a real phone screen" : "Voice isn't configured on this server"}</small></span></button>
            <button type="button" className={`format-card ${!useVoiceOnly ? "selected" : ""}`} onClick={() => chooseVoice(false)} aria-pressed={!useVoiceOnly}><Keyboard size={18} /><span><strong>{voiceAvailable ? "Voice + text" : "Text"}</strong><small>See each question; speak or type your answer</small></span></button>
          </div>
          <label className={`toggle-row ${rules.camera_required ? "locked" : ""}`}><input type="checkbox" checked={proctored} disabled={rules.camera_required} onChange={(event) => chooseCamera(event.target.checked)} /><span className="toggle" /><span><strong>Camera & face tracking</strong><small>{rules.camera_required ? "Required for assessments. " : ""}Warns you if you leave the frame or look away. Runs only in your browser.</small></span></label>
        </section>
      </div>
      <aside className="setup-summary panel">
        <span className="eyebrow">YOUR INTERVIEW</span>
        <h2>{roleTitle}</h2>
        <dl><div><dt>Level</dt><dd>{LEVELS.find((item) => item.key === level)?.title}</dd></div><div><dt>Session</dt><dd>{mode === "assessment" ? "Assessment" : "Practice"}</dd></div><div><dt>Questions</dt><dd>{rules.questions} + follow-ups</dd></div><div><dt>Time</dt><dd>~{rules.minutes} min</dd></div><div><dt>Format</dt><dd>{useVoiceOnly ? "Voice call" : voiceAvailable ? "Voice + text" : "Text"}</dd></div><div><dt>Camera</dt><dd>{proctored ? "On" : "Off"}</dd></div>{focus.length > 0 && <div><dt>Focus</dt><dd>{focus.join(", ")}</dd></div>}</dl>
        {error && <div className="notice error-notice">{error}</div>}
        <button className="button primary start-button" onClick={() => void begin()} disabled={pending}>{pending ? <><Loader2 size={16} className="spin" />Alex is preparing your questions…</> : <>Continue to device check <ArrowRight size={16} /></>}</button>
        <p className="small-muted" aria-live="polite">{saveNote || "Your choices are saved to your account."}</p>
      </aside>
    </div>
  </div>;
}
