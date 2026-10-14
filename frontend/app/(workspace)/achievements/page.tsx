"use client";

import useSWR from "swr";
import { ArrowRight, Award, Check, LockKeyhole, Sparkles } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

type Achievement = { id: string; title: string; description: string; unlocked: boolean };
export default function AchievementsPage() {
  const { data, error, isLoading } = useSWR<{ achievements: Achievement[] }>("/achievements", (path: string) => api<{ achievements: Achievement[] }>(path));
  const unlocked = data?.achievements.filter((item) => item.unlocked).length ?? 0;
  return <><div className="page-heading"><div><span className="eyebrow">MILESTONES</span><h1>Small wins add up.</h1><p>These milestones recognize the habits that make practice stick.</p></div><span className="achievement-count"><Award size={17} />{unlocked} unlocked</span></div>{error && <div className="notice error-notice">Milestones could not be loaded. Try refreshing.</div>}{isLoading ? <div className="centered-state">Loading milestones…</div> : <div className="achievement-grid">{data?.achievements.map((item) => <article className={`achievement-card ${item.unlocked ? "unlocked" : "locked"}`} key={item.id}><span className="achievement-icon">{item.unlocked ? <Check size={19} /> : <LockKeyhole size={17} />}</span><span className="eyebrow">{item.unlocked ? "UNLOCKED" : "IN PROGRESS"}</span><h2>{item.title}</h2><p>{item.description}</p></article>)}</div>}<div className="achievement-nudge"><Sparkles size={18} /><span>Ready for another?</span><Link href="/practice">Choose a practice round <ArrowRight size={15} /></Link></div></>;
}
