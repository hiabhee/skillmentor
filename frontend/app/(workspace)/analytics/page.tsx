"use client";

import useSWR from "swr";
import { ArrowUpRight, BarChart3, Sparkles } from "lucide-react";
import { api } from "@/lib/api";

type Analytics = { average_score: number | null; by_type: { type: string; average: number; responses: number }[]; daily: { date: string; average: number; responses: number }[] };
export default function AnalyticsPage() {
  const { data, error, isLoading } = useSWR<Analytics>("/analytics", (path: string) => api<Analytics>(path));
  const max = Math.max(10, ...(data?.daily.map((item) => item.average) ?? []));
  return <>
    <div className="page-heading"><div><span className="eyebrow">YOUR DEVELOPMENT</span><h1>Notice the progress.</h1><p>Patterns over time can show you where your practice is paying off.</p></div></div>
    {error && <div className="notice error-notice">Progress could not be loaded. Try refreshing.</div>}
    <div className="analytics-overview"><section className="panel score-panel"><span className="eyebrow">OVERALL AVERAGE</span><div className="score-big">{isLoading ? "—" : data?.average_score == null ? "—" : data.average_score}<small>{data?.average_score == null ? "" : "/10"}</small></div><p>{data?.average_score == null ? "Complete a scored response to see your average." : "A useful signal. Keep looking at the feedback behind the number, too."}</p><div className="score-decoration"><Sparkles size={24} /></div></section><section className="panel category-panel"><div className="panel-heading"><div><span className="eyebrow">BY PRACTICE TYPE</span><h3>Where you’ve focused</h3></div><BarChart3 size={17} /></div>{data?.by_type.length ? data.by_type.map((item) => <div className="type-score" key={item.type}><div><strong>{item.type}</strong><span>{item.responses} responses</span></div><b>{item.average}<small> / 10</small></b><div className="mini-track"><i style={{ width: `${item.average * 10}%` }} /></div></div>) : <div className="empty-inline">Your practice breakdown will appear here.</div>}</section></div>
    <section className="panel trend-panel"><div className="panel-heading"><div><span className="eyebrow">RESPONSE SCORES</span><h3>Your recent trend</h3></div><span className="chart-legend"><i /> Average score</span></div>{isLoading ? <div className="empty-inline">Loading…</div> : data?.daily.length ? <div className="chart-area" role="img" aria-label="Average response score by day">{data.daily.slice(-14).map((item) => <div className="chart-column" key={item.date} title={`${item.date}: ${item.average}/10`}><span className="chart-value">{item.average}</span><div className="chart-bar-wrap"><i style={{ height: `${Math.max(4, (item.average / max) * 100)}%` }} /></div><span className="chart-day">{new Date(item.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span></div>)}</div> : <div className="empty-state compact-empty"><span className="empty-icon"><BarChart3 size={20} /></span><strong>Your trend starts with your next session.</strong><p>Scores from your reviewed responses will show here.</p></div>}<div className="chart-footnote"><ArrowUpRight size={14} /> Scores are automated estimates. Use written feedback and your own review to guide changes.</div></section>
  </>;
}
