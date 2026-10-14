"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, CircleAlert, Lightbulb, Loader2, RotateCcw, ShieldCheck, Target, TrendingUp, Trophy } from "lucide-react";
import { api, feedbackObject } from "@/lib/api";
import { type Report, scoreTone, type TechSession } from "@/lib/interview";

const EVENT_LABEL: Record<string, string> = { no_face: "Out of frame", multiple_faces: "Another person in view", looking_away: "Looking away", tab_hidden: "Left the tab", camera_off: "Camera off" };

function ScoreRing({ score }: { score: number }) {
  const radius = 54, circumference = 2 * Math.PI * radius;
  return <div className={`score-ring tone-${scoreTone(score)}`}>
    <svg viewBox="0 0 128 128" aria-hidden="true"><circle cx="64" cy="64" r={radius} className="ring-track" /><circle cx="64" cy="64" r={radius} className="ring-value" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - score / 10)} /></svg>
    <div><strong>{score.toFixed(1)}</strong><span>out of 10</span></div>
  </div>;
}

export function TechReport({ session, refresh }: { session: TechSession; refresh: () => Promise<unknown> }) {
  const [report, setReport] = useState<Report | null>(session.report);
  const [error, setError] = useState("");
  const requested = useRef(false);
  useEffect(() => {
    if (report || requested.current) return;
    requested.current = true;
    api<{ report: Report }>(`/interviews/${session.id}/report`, { method: "POST" })
      .then((result) => { setReport(result.report); void refresh(); })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Your report could not be generated."));
  }, [report, refresh, session.id]);

  if (!report) return <div className="report-loading">{error ? <><CircleAlert size={26} /><h2>Report unavailable</h2><p>{error}</p><button className="button secondary" onClick={() => { requested.current = false; setError(""); setReport(null); window.location.reload(); }}>Try again</button></> : <><Loader2 size={30} className="spin" /><h2>Alex is writing your report…</h2><p>Scoring each answer and comparing it with what strong {session.level_label.toLowerCase()} candidates say.</p></>}</div>;

  const integrity = report.integrity;
  const assessment = session.mode === "assessment";
  return <div className="report">
    <section className="report-hero">
      <ScoreRing score={report.overall_score} />
      <div className="report-hero-copy">
        <span className="eyebrow">{assessment ? "ASSESSMENT RESULT" : "PRACTICE REPORT"} · {session.level_label.toUpperCase()}</span>
        <h1>{session.role}</h1>
        {assessment && <span className={`verdict verdict-${report.verdict.toLowerCase().replace(/\s+/g, "-")}`}><Trophy size={14} />{report.verdict}</span>}
        <p>{report.summary}</p>
        <div className="report-actions"><Link className="button primary" href={`/practice/interview?mode=practice&role=${encodeURIComponent(session.role)}`}><RotateCcw size={15} />Practice again</Link>{!assessment && <Link className="button secondary" href="/practice/interview?mode=assessment">Take an assessment <ArrowRight size={15} /></Link>}<Link className="button quiet" href="/">Dashboard</Link></div>
      </div>
    </section>

    <div className={`report-grid ${integrity.monitored ? "" : "single"}`}>
      <section className="panel report-card"><div className="report-card-title"><Target size={16} /><h3>Competencies</h3></div>
        {report.competencies.map((item) => <div className="competency" key={item.key}><div><strong>{item.name}</strong><b className={`tone-text-${scoreTone(item.score)}`}>{item.score.toFixed(1)}</b></div><div className="competency-track"><i className={`tone-bg-${scoreTone(item.score)}`} style={{ width: `${item.score * 10}%` }} /></div></div>)}
      </section>
      {integrity.monitored && <section className={`panel report-card integrity-${integrity.status}`}><div className="report-card-title"><ShieldCheck size={16} /><h3>Interview integrity</h3></div>
        <p className="integrity-status">{integrity.status === "clean" ? "Clean session: you stayed focused the whole time." : integrity.status === "minor" ? "A few brief interruptions were noticed." : "Several interruptions were noticed. In a real interview these could raise concerns."}</p>
        {Object.entries(integrity.events).map(([kind, value]) => <div className="integrity-row" key={kind}><span>{EVENT_LABEL[kind] ?? kind}</span><b>{value.count}× · {value.seconds}s</b></div>)}
      </section>}
    </div>

    <div className="report-columns">
      <section className="panel report-card"><div className="report-card-title"><Check size={16} /><h3>Strengths</h3></div>{report.strengths.map((item) => <p className="report-point good" key={item}>{item}</p>)}</section>
      <section className="panel report-card"><div className="report-card-title"><TrendingUp size={16} /><h3>To improve</h3></div>{report.improvements.map((item) => <p className="report-point improve" key={item}>{item}</p>)}</section>
      {report.next_steps?.length ? <section className="panel report-card"><div className="report-card-title"><Lightbulb size={16} /><h3>Study next</h3></div>{report.next_steps.map((item) => <p className="report-point next" key={item}>{item}</p>)}</section> : null}
    </div>

    <section className="panel transcript"><div className="panel-heading"><div><span className="eyebrow">QUESTION BY QUESTION</span><h3>Your interview, replayed</h3></div></div>
      {session.turns.map((turn) => { const feedback = feedbackObject(turn.feedback) as (ReturnType<typeof feedbackObject> & { model_answer?: string[] }) | null; return <details className="transcript-row" key={turn.id}>
        <summary><span className={`score-chip tone-${scoreTone(turn.score)}`}>{turn.score ?? "—"}</span><span><strong>{turn.question}</strong><small>{turn.category_label}{turn.is_follow_up ? " · follow-up" : ""}</small></span><ChevronDown size={15} /></summary>
        <div className="transcript-body"><p className="transcript-answer">{turn.answer}</p>
          {feedback?.strengths?.map((item) => <p className="report-point good" key={item}>{item}</p>)}
          {feedback?.improvements?.map((item) => <p className="report-point improve" key={item}>{item}</p>)}
          {feedback?.model_answer?.length ? <div className="model-answer"><strong>A strong answer covers</strong>{feedback.model_answer.map((item) => <p key={item}><Lightbulb size={13} />{item}</p>)}</div> : null}
        </div></details>; })}
    </section>
    {!report.automated && <p className="small-muted center">Parts of this report were calculated without the AI service.</p>}
  </div>;
}
