"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { ArrowLeft, ArrowRight, Check, MessageCircleMore, RotateCcw, Sparkles } from "lucide-react";
import { api, feedbackObject } from "@/lib/api";
import { VoiceControls } from "@/components/VoiceControls";
import { TechSession } from "@/components/tech/TechSession";
import type { TechSession as TechSessionData } from "@/lib/interview";

type Challenge = { title: string; description: string; difficulty: string; topic: string; constraints: string[]; examples: { input: string; output: string }[]; starter_code: string };
type Answer = { id: number; position: number; question: string; answer: string; feedback: string | null; score: number | null };
type Session = { id: number; type: "round1" | "coding"; status: string; average_score: number | null; voice_enabled?: boolean; next_question?: { position: number; total: number; question: string }; next_challenge?: { position: number; total: number; challenge: Challenge } | null; responses: Answer[] };
type InterviewPayload = { interview: Session | TechSessionData };

export default function SessionPage() {
  const params = useParams<{ id: string }>(); const id = Number(params.id);
  const { data, error, isLoading, mutate } = useSWR<InterviewPayload>(Number.isFinite(id) ? `/interviews/${id}` : null, (path: string) => api<InterviewPayload>(path));
  if (isLoading) return <div className="centered-state">Loading your session…</div>;
  if (error || !data?.interview) return <div className="centered-state"><h2>Session unavailable</h2><p>This session may have been removed or belongs to another account.</p><Link href="/practice" className="button secondary">Back to practice</Link></div>;
  if (data.interview.type === "tech") return <TechSession session={data.interview} refresh={mutate} />;
  const session = data.interview;
  return <>
    <Link className="back-link" href="/practice"><ArrowLeft size={15} /> Practice library</Link>
    <div className="session-heading"><div><span className="eyebrow">{session.type === "round1" ? "PERSONAL INTERVIEW" : "CODING PRACTICE"} · SESSION {session.id}</span><h1>{session.status === "completed" ? "A session well spent." : session.type === "round1" ? "Take a moment. Then answer." : "Work through the problem."}</h1><p>{session.status === "completed" ? "Review your responses and the notes from each round." : "Your responses save as you go."}</p></div><span className={`status-tag ${session.status === "completed" ? "complete-tag" : ""}`}>{session.status === "completed" ? "Completed" : "In progress"}</span></div>
    {session.status === "completed" ? <Completed session={session} /> : session.type === "round1" ? <InterviewStep session={session} refresh={mutate} /> : <CodingStep session={session} refresh={mutate} />}
    {session.status !== "completed" && <p className="session-footnote"><Sparkles size={13} /> Automated feedback is a coaching aid. Use your judgment and verify code independently.</p>}
  </>;
}

function InterviewStep({ session, refresh }: { session: Session; refresh: () => Promise<unknown> }) {
  const step = session.next_question; const [answer, setAnswer] = useState(""); const [review, setReview] = useState<Record<string, unknown> | null>(null); const [pending, setPending] = useState(false); const [error, setError] = useState("");
  if (!step) return <Completed session={session} />;
  async function submit(skip = false) {
    setPending(true); setError("");
    try {
      const result = await api<{ feedback: Record<string, unknown>; completed: boolean; average_score: number }>(`/interviews/${session.id}/answers`, { method: "POST", body: JSON.stringify({ answer, skip }) });
      setReview(result.feedback); setAnswer(""); await refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Your answer could not be saved."); }
    finally { setPending(false); }
  }
  function handleSubmit(event: FormEvent) { event.preventDefault(); void submit(false); }
  return <div className="session-grid"><section className="panel session-panel"><div className="step-top"><span>QUESTION {String(step.position + 1).padStart(2, "0")} <i /> {String(step.total).padStart(2, "0")}</span><span>{Math.round((step.position / step.total) * 100)}% complete</span></div><div className="progress-track"><div style={{ width: `${(step.position / step.total) * 100}%` }} /></div><div className="question-block"><span className="question-icon"><MessageCircleMore size={19} /></span><span className="eyebrow">TAKE YOUR TIME</span><h2>{step.question}</h2><p>Make the moment specific. What was happening, what did you do, and what changed?</p>{session.voice_enabled && <VoiceControls key={step.position} interviewId={session.id} position={step.position} disabled={pending} onTranscript={(text) => setAnswer((current) => (current.trim() ? `${current.trim()} ${text}` : text).slice(0, 20000))} />}</div>
    {review && <ReviewCard feedback={review} label="ANSWER REVIEW" />}
    <form onSubmit={handleSubmit} className="answer-form"><label className="field-label" htmlFor="answer">Your answer</label><textarea id="answer" value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder={session.voice_enabled ? "Answer by voice or write your response here…" : "Write your response here…"} maxLength={20000} rows={8} disabled={pending} /><div className="answer-tools"><span>{answer.length.toLocaleString()} / 20,000</span><div>{error && <span className="inline-error">{error}</span>}<button type="button" className="button quiet" onClick={() => void submit(true)} disabled={pending}>Skip question</button><button className="button primary" disabled={pending || !answer.trim()}>{pending ? "Reviewing…" : "Submit answer"}<ArrowRight size={15} /></button></div></div></form>
    </section><aside className="panel side-tip"><span className="eyebrow">A SIMPLE FRAMEWORK</span><h3>Keep it grounded.</h3><ol><li><span>01</span><div><strong>Set the scene</strong><small>Give just enough context.</small></div></li><li><span>02</span><div><strong>Own your action</strong><small>Be clear about your contribution.</small></div></li><li><span>03</span><div><strong>Show the outcome</strong><small>Describe impact or what you learned.</small></div></li></ol><div className="tip-note">A concise, concrete answer is easier to remember and easier to assess.</div></aside></div>;
}

function CodingStep({ session, refresh }: { session: Session; refresh: () => Promise<unknown> }) {
  const step = session.next_challenge; const [editor, setEditor] = useState({ position: step?.position ?? -1, code: step?.challenge.starter_code ?? "" }); const [review, setReview] = useState<Record<string, unknown> | null>(null); const [pending, setPending] = useState(false); const [error, setError] = useState("");
  if (!step) return <Completed session={session} />;
  const currentStep = step;
  const code = editor.position === currentStep.position ? editor.code : currentStep.challenge.starter_code;
  const challenge = currentStep.challenge;
  async function submit(event: FormEvent) {
    event.preventDefault(); setPending(true); setError("");
    try { const result = await api<{ evaluation: Record<string, unknown> }>(`/interviews/${session.id}/submissions`, { method: "POST", body: JSON.stringify({ code, position: currentStep.position }) }); setReview(result.evaluation); await refresh(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Your code could not be reviewed."); }
    finally { setPending(false); }
  }
  return <div className="coding-workspace"><div className="coding-main"><div className="step-top"><span>CHALLENGE {step.position + 1} <i /> {step.total}</span><span>{challenge.difficulty} · {challenge.topic}</span></div><div className="progress-track"><div style={{ width: `${(step.position / step.total) * 100}%` }} /></div><div className="problem-copy"><h2>{challenge.title}</h2><p>{challenge.description}</p><h3>Constraints</h3><ul>{challenge.constraints.map((item) => <li key={item}>{item}</li>)}</ul><h3>Examples</h3>{challenge.examples.map((example, index) => <div className="example-card" key={index}><strong>Example {index + 1}</strong><div><span>Input</span><pre>{example.input}</pre></div><div><span>Output</span><pre>{example.output}</pre></div></div>)}</div></div>
    <form className="code-editor-panel" onSubmit={submit}><div className="editor-top"><div><span className="editor-dot" /><strong>solution.py</strong></div><span>Python 3</span></div><textarea aria-label="Python solution" spellCheck={false} value={code} onChange={(event) => setEditor({ position: currentStep.position, code: event.target.value })} maxLength={100000} rows={25} /><div className="editor-bottom">{error && <span className="inline-error">{error}</span>}<span className="editor-hint">Your code is reviewed by an AI coach. It is not executed.</span><button className="button primary" disabled={pending || !code.trim()}>{pending ? "Reviewing…" : "Submit solution"}<ArrowRight size={15} /></button></div>{review && <ReviewCard feedback={review} label="CODE REVIEW" />}</form>
  </div>;
}

function ReviewCard({ feedback, label }: { feedback: Record<string, unknown>; label: string }) {
  const referenceSolution = typeof feedback.reference_solution === "string" ? feedback.reference_solution : null;
  const strengths = Array.isArray(feedback.strengths) ? feedback.strengths as string[] : [];
  const improvements = Array.isArray(feedback.improvements) ? feedback.improvements as string[] : [];
  return <div className="review-card"><div className="review-header"><span className="review-icon"><Sparkles size={15} /></span><span className="eyebrow">{label}</span>{typeof feedback.score === "number" && <strong className="review-score">{feedback.score}<small> / 10</small></strong>}</div>{typeof feedback.summary === "string" && <p className="review-summary">{feedback.summary}</p>}{strengths.length > 0 && <div className="review-points"><strong>What worked</strong>{strengths.map((item) => <p key={item}><Check size={14} />{item}</p>)}</div>}{improvements.length > 0 && <div className="review-points improvements"><strong>Try next</strong>{improvements.map((item) => <p key={item}><ArrowRight size={14} />{item}</p>)}</div>}{referenceSolution && <details className="solution-details"><summary>View reference solution</summary><pre>{referenceSolution}</pre></details>}{feedback.automated === false && <span className="small-muted">A basic review was used because the AI service was unavailable.</span>}</div>;
}

function Completed({ session }: { session: Session }) {
  const average = session.average_score;
  return <div className="completed-wrap"><section className="panel completed-panel"><span className="complete-icon"><Check size={24} /></span><span className="eyebrow">SESSION COMPLETE</span><h2>That’s another rep in the bank.</h2><p>You can revisit every answer, submission, and review in your session history.</p><div className="complete-stat"><span>Average reviewed score</span><strong>{average == null ? "Not scored" : `${average} / 10`}</strong></div><div className="complete-actions"><Link href="/history" className="button primary">View history <ArrowRight size={15} /></Link><Link href="/practice" className="button secondary"><RotateCcw size={15} />Practice again</Link></div></section>{session.responses.length > 0 && <section className="panel response-review-list"><div className="panel-heading"><div><span className="eyebrow">SESSION NOTES</span><h3>Your responses</h3></div></div>{session.responses.map((item) => <details className="response-review-row" key={item.id}><summary><span className="review-row-check"><Check size={14} /></span><span><strong>{item.question}</strong><small>{item.score == null ? "Not scored" : `Score ${item.score} / 10`}</small></span><ArrowRight size={15} /></summary><div className="response-detail"><p className="response-answer">{item.answer}</p><ReviewCard feedback={feedbackObject(item.feedback) ?? { summary: "Review unavailable" }} label="REVIEW" /></div></details>)}</section>}</div>;
}
