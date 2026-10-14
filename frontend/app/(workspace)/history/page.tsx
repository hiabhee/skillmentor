"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { ArrowRight, Code2, MessageCircleMore, Trash2 } from "lucide-react";
import { api } from "@/lib/api";

type Item = { id: number; interview_id: number; type: string; label?: string; question: string; answer: string; feedback: string | null; score: number | null; created_at: string };
export default function HistoryPage() {
  const { data, error, isLoading, mutate } = useSWR<{ responses: Item[] }>("/history", (path: string) => api<{ responses: Item[] }>(path));
  const [busy, setBusy] = useState<number | "all" | null>(null);
  async function remove(id: number) { setBusy(id); try { await api(`/history/${id}`, { method: "DELETE" }); await mutate(); } finally { setBusy(null); } }
  async function clearAll() { if (!window.confirm("Delete all saved responses? This cannot be undone.")) return; setBusy("all"); try { await api("/history", { method: "DELETE" }); await mutate(); } finally { setBusy(null); } }
  return <>
    <div className="page-heading"><div><span className="eyebrow">YOUR PRACTICE LOG</span><h1>History that helps you improve.</h1><p>Review what you said, what worked, and what to try next.</p></div>{data?.responses.length ? <button className="button quiet danger-quiet" onClick={clearAll} disabled={busy !== null}><Trash2 size={15} />Clear history</button> : null}</div>
    {error && <div className="notice error-notice">Your history could not be loaded. Try refreshing.</div>}
    <section className="panel history-panel">{isLoading ? <div className="centered-state">Loading your history…</div> : data?.responses.length ? <div className="history-list">{data.responses.map((item) => <article className="history-item" key={item.id}><div className="history-type-icon">{item.type === "coding" ? <Code2 size={17} /> : <MessageCircleMore size={17} />}</div><div className="history-main"><div className="history-title-row"><Link href={`/sessions/${item.interview_id}`}><strong>{item.question}</strong><ArrowRight size={14} /></Link><span className="history-score">{item.score == null ? "—" : `${item.score}/10`}</span></div><div className="history-meta"><span>{item.label ?? (item.type === "round1" ? "Personal interview" : "Coding practice")}</span><span>·</span><time>{new Date(item.created_at).toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric" })}</time></div><details className="history-answer"><summary>View response and feedback</summary><p>{item.answer}</p>{item.feedback && <blockquote>{(() => { try { const parsed = JSON.parse(item.feedback); return parsed.summary || [...(parsed.strengths || []), ...(parsed.improvements || [])].join(" "); } catch { return item.feedback; } })()}</blockquote>}</details></div><button className="icon-button delete-button" onClick={() => void remove(item.id)} disabled={busy !== null} aria-label="Delete history item"><Trash2 size={15} /></button></article>)}</div> : <div className="empty-state"><span className="empty-icon"><MessageCircleMore size={20} /></span><strong>No responses saved yet.</strong><p>When you practice, your answers and feedback will appear here.</p><Link className="button secondary" href="/practice">Explore practice <ArrowRight size={15} /></Link></div>}</section>
  </>;
}
