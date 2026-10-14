"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Braces } from "lucide-react";
import { api } from "@/lib/api";

export default function CodingStartPage() {
  const [pending, setPending] = useState(false); const [error, setError] = useState(""); const router = useRouter();
  async function start() { setPending(true); setError(""); try { const result = await api<{ interview: { id: number } }>("/interviews", { method: "POST", body: JSON.stringify({ type: "coding" }) }); router.push(`/sessions/${result.interview.id}`); } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start your session."); setPending(false); } }
  return <div className="session-intro"><div className="intro-visual code-visual"><Braces size={31} strokeWidth={1.4} /><span className="visual-orbit orbit-one" /><span className="visual-orbit orbit-two" /></div><span className="eyebrow">CODING PRACTICE · 3 CHALLENGES</span><h1>Think through the edge cases.</h1><p className="intro-lede">A short set of algorithm problems with examples, constraints, and structured review to help sharpen your approach.</p><div className="intro-details"><div><span>01</span><strong>Read the full prompt</strong><small>Use the examples and constraints to frame your solution.</small></div><div><span>02</span><strong>Write and submit code</strong><small>Python is the expected language for these challenges.</small></div><div><span>03</span><strong>Review the reasoning</strong><small>Automated feedback may miss details; verify your own cases.</small></div></div>{error && <div className="notice error-notice">{error}</div>}<button className="button primary" onClick={start} disabled={pending}>{pending ? "Starting…" : "Begin coding practice"}<ArrowRight size={16} /></button><p className="small-muted">Your code is stored with your session history.</p></div>;
}
