"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { ArrowRight, AudioLines, BrainCircuit, Check, ClipboardCheck, Cloud, Database, GraduationCap, Keyboard, Layers, Loader2, Monitor, PenLine, ScanFace, Server, ShieldCheck, Smartphone, Sparkles, Timer } from "lucide-react";
import { api } from "@/lib/api";
import { type Level, LEVELS, type Mode, type RoleKey, ROLES } from "@/lib/interview";

const ROLE_ICONS: Record<RoleKey, typeof Monitor> = { frontend: Monitor, backend: Server, fullstack: Layers, mobile: Smartphone, data: Database, ml: BrainCircuit, devops: Cloud, security: ShieldCheck, custom: PenLine };
type Capabilities = { voice: boolean; ai: boolean };

export default function InterviewSetupPage() {
  return <Suspense fallback={<div className="centered-state">Loading…</div>}><InterviewSetup /></Suspense>;
}

function initialRole(param: string | null): { key: RoleKey; custom: string } {
  if (!param) return { key: "backend", custom: "" };
  const match = ROLES.find((role) => role.key === param || role.full.toLowerCase() === param.toLowerCase());
  return match ? { key: match.key, custom: "" } : { key: "custom", custom: param.slice(0, 60) };
}

function InterviewSetup() {
  const params = useSearchParams();
  const router = useRouter();
  const { data: caps } = useSWR<Capabilities>("/capabilities", (path: string) => api<Capabilities>(path));
  const start = initialRole(params.get("role"));
  const [role, setRole] = useState<RoleKey>(start.key);
  const [customRole, setCustomRole] = useState(start.custom);
  const [level, setLevel] = useState<Level>("mid");
  const [focus, setFocus] = useState<string[]>([]);
  const [mode, setMode] = useState<Mode>(params.get("mode") === "assessment" ? "assessment" : "practice");
  const [voiceOnly, setVoiceOnly] = useState(true);
  const [camera, setCamera] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  const roleInfo = ROLES.find((item) => item.key === role)!;
  const voiceAvailable = caps?.voice ?? false;
  const useVoiceOnly = voiceAvailable && voiceOnly;
  const proctored = mode === "assessment" || camera;
  const count = mode === "assessment" ? 8 : 6;
  const roleTitle = role === "custom" ? customRole.trim() || "Your role" : roleInfo.full;

  function chooseRole(key: RoleKey) { setRole(key); setFocus([]); }
  function toggleFocus(item: string) { setFocus((current) => current.includes(item) ? current.filter((value) => value !== item) : current.length >= 3 ? current : [...current, item]); }

  async function begin() {
    if (role === "custom" && customRole.trim().length < 2) { setError("Type the role you're interviewing for."); return; }
    setPending(true); setError("");
    try {
      const result = await api<{ interview: { id: number } }>("/interviews", { method: "POST", body: JSON.stringify({ type: "tech", role, custom_role: customRole.trim(), level, mode, focus: focus.join(", "), voice_only: useVoiceOnly, proctored }) });
      router.push(`/sessions/${result.interview.id}`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start your interview."); setPending(false); }
  }

  return <div className="setup">
    <div className="page-heading"><div><span className="eyebrow">BUILD YOUR INTERVIEW</span><h1>What role are you going after?</h1><p>Alex, your AI interviewer, tailors every question to the role, level and topics you choose.</p></div></div>
    <div className="setup-grid">
      <div className="setup-steps">
        <section className="setup-step"><div className="step-label"><span>1</span>Role</div>
          <div className="role-grid">{ROLES.map((item) => { const Icon = ROLE_ICONS[item.key]; return <button type="button" key={item.key} className={`role-card ${role === item.key ? "selected" : ""}`} onClick={() => chooseRole(item.key)} aria-pressed={role === item.key}><span className="role-icon"><Icon size={19} /></span><strong>{item.title}</strong><small>{item.blurb}</small>{role === item.key && <span className="role-check"><Check size={12} /></span>}</button>; })}</div>
          {role === "custom" && <input className="text-input" value={customRole} onChange={(event) => setCustomRole(event.target.value)} maxLength={60} placeholder="e.g. Platform Engineer, Game Developer, QA Automation" autoFocus />}
        </section>
        <section className="setup-step"><div className="step-label"><span>2</span>Level</div>
          <div className="segmented">{LEVELS.map((item) => <button type="button" key={item.key} className={level === item.key ? "selected" : ""} onClick={() => setLevel(item.key)} aria-pressed={level === item.key}><strong>{item.title}</strong><small>{item.years}</small></button>)}</div>
        </section>
        <section className="setup-step"><div className="step-label"><span>3</span>Focus areas <em>optional · up to 3</em></div>
          <div className="chip-row">{roleInfo.focus.map((item) => <button type="button" key={item} className={`chip ${focus.includes(item) ? "selected" : ""}`} onClick={() => toggleFocus(item)} aria-pressed={focus.includes(item)}>{focus.includes(item) && <Check size={12} />}{item}</button>)}</div>
        </section>
        <section className="setup-step"><div className="step-label"><span>4</span>Session type</div>
          <div className="mode-grid">
            <button type="button" className={`mode-card ${mode === "practice" ? "selected" : ""}`} onClick={() => setMode("practice")} aria-pressed={mode === "practice"}><GraduationCap size={22} /><strong>Practice</strong><span>Coaching after every answer, model answers, no clock. Learn as you go.</span><ul><li><Check size={12} />6 questions</li><li><Check size={12} />Instant feedback</li><li><Check size={12} />Camera optional</li></ul></button>
            <button type="button" className={`mode-card assessment ${mode === "assessment" ? "selected" : ""}`} onClick={() => setMode("assessment")} aria-pressed={mode === "assessment"}><ClipboardCheck size={22} /><strong>Assessment</strong><span>Real interview conditions. Timed answers, results only at the end, and a hire verdict.</span><ul><li><Timer size={12} />8 questions · 3 min each</li><li><ScanFace size={12} />Face tracking on</li><li><Sparkles size={12} />Scorecard & verdict</li></ul></button>
          </div>
        </section>
        <section className="setup-step"><div className="step-label"><span>5</span>Format</div>
          <div className="format-row">
            <button type="button" className={`format-card ${useVoiceOnly ? "selected" : ""}`} onClick={() => setVoiceOnly(true)} disabled={!voiceAvailable} aria-pressed={useVoiceOnly}><AudioLines size={18} /><span><strong>Voice call</strong><small>{voiceAvailable ? "Hands-free and spoken only, like a real phone screen" : "Voice isn't configured on this server"}</small></span></button>
            <button type="button" className={`format-card ${!useVoiceOnly ? "selected" : ""}`} onClick={() => setVoiceOnly(false)} aria-pressed={!useVoiceOnly}><Keyboard size={18} /><span><strong>{voiceAvailable ? "Voice + text" : "Text"}</strong><small>See each question; speak or type your answer</small></span></button>
          </div>
          <label className={`toggle-row ${mode === "assessment" ? "locked" : ""}`}><input type="checkbox" checked={proctored} disabled={mode === "assessment"} onChange={(event) => setCamera(event.target.checked)} /><span className="toggle" /><span><strong>Camera & face tracking</strong><small>{mode === "assessment" ? "Required for assessments. " : ""}Warns you if you leave the frame or look away. Runs only in your browser.</small></span></label>
        </section>
      </div>
      <aside className="setup-summary panel">
        <span className="eyebrow">YOUR INTERVIEW</span>
        <h2>{roleTitle}</h2>
        <dl><div><dt>Level</dt><dd>{LEVELS.find((item) => item.key === level)?.title}</dd></div><div><dt>Session</dt><dd>{mode === "assessment" ? "Assessment" : "Practice"}</dd></div><div><dt>Questions</dt><dd>{count} + follow-ups</dd></div><div><dt>Time</dt><dd>~{mode === "assessment" ? 25 : 15} min</dd></div><div><dt>Format</dt><dd>{useVoiceOnly ? "Voice call" : voiceAvailable ? "Voice + text" : "Text"}</dd></div><div><dt>Camera</dt><dd>{proctored ? "On" : "Off"}</dd></div>{focus.length > 0 && <div><dt>Focus</dt><dd>{focus.join(", ")}</dd></div>}</dl>
        {error && <div className="notice error-notice">{error}</div>}
        <button className="button primary start-button" onClick={() => void begin()} disabled={pending}>{pending ? <><Loader2 size={16} className="spin" />Alex is preparing your questions…</> : <>Continue to device check <ArrowRight size={16} /></>}</button>
        <p className="small-muted">Your answers stay private in your history.</p>
      </aside>
    </div>
  </div>;
}
