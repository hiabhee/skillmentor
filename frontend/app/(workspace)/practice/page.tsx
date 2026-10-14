import Link from "next/link";
import { ArrowUpRight, AudioLines, Braces, ClipboardCheck, GraduationCap, MoveRight, ScanFace, Timer, Zap } from "lucide-react";
import { ROLES } from "@/lib/interview";

export default function PracticePage() {
  return <>
    <div className="page-heading"><div><span className="eyebrow">TECH INTERVIEW STUDIO</span><h1>What are we training today?</h1><p>Mock interviews with an AI interviewer who listens, asks follow-ups and tells you exactly what to fix.</p></div></div>
    <div className="hub-grid">
      <Link href="/practice/interview?mode=practice" className="hub-card hub-practice"><span className="hub-top"><span className="hub-icon"><GraduationCap size={22} /></span><ArrowUpRight size={18} /></span><span className="eyebrow">LEARN</span><h2>Practice interview</h2><p>Role-specific questions with coaching and a model answer after every response.</p><span className="hub-meta"><span><AudioLines size={13} />Voice or text</span><span><Zap size={13} />Instant feedback</span></span><span className="hub-cta">Start practicing <MoveRight size={16} /></span></Link>
      <Link href="/practice/interview?mode=assessment" className="hub-card hub-assessment"><span className="hub-top"><span className="hub-icon"><ClipboardCheck size={22} /></span><ArrowUpRight size={18} /></span><span className="eyebrow">PROVE IT</span><h2>Assessment</h2><p>Real interview conditions: timed answers, face tracking, then a scorecard and a hire verdict.</p><span className="hub-meta"><span><Timer size={13} />~25 min</span><span><ScanFace size={13} />Proctored</span></span><span className="hub-cta">Take an assessment <MoveRight size={16} /></span></Link>
      <Link href="/practice/coding" className="hub-card hub-coding"><span className="hub-top"><span className="hub-icon"><Braces size={22} /></span><ArrowUpRight size={18} /></span><span className="eyebrow">CODE</span><h2>Coding challenges</h2><p>Hard algorithm problems with an AI review of correctness, edge cases and complexity.</p><span className="hub-meta"><span><Timer size={13} />3 problems</span><span>Python</span></span><span className="hub-cta">Open the editor <MoveRight size={16} /></span></Link>
    </div>
    <div className="section-head"><div><span className="eyebrow">JUMP STRAIGHT IN</span><h2>Practice by role</h2></div></div>
    <div className="role-strip">{ROLES.filter((role) => role.key !== "custom").map((role) => <Link key={role.key} href={`/practice/interview?mode=practice&role=${role.key}`} className="role-pill"><strong>{role.title}</strong><small>{role.focus.slice(0, 2).join(" · ")}</small></Link>)}</div>
  </>;
}
