export type RoleKey = "frontend" | "backend" | "fullstack" | "mobile" | "data" | "ml" | "devops" | "security" | "custom";
export type Level = "intern" | "junior" | "mid" | "senior" | "staff";
export type Mode = "practice" | "assessment";

export const ROLES: { key: RoleKey; title: string; full: string; blurb: string; focus: string[] }[] = [
  { key: "frontend", full: "Frontend Engineer", title: "Frontend", blurb: "React, browser internals, performance, accessibility", focus: ["React", "TypeScript", "Web performance", "Accessibility", "CSS architecture"] },
  { key: "backend", full: "Backend Engineer", title: "Backend", blurb: "APIs, databases, scalability, distributed systems", focus: ["System design", "SQL & indexing", "Caching", "Concurrency", "API design"] },
  { key: "fullstack", full: "Full-Stack Engineer", title: "Full-stack", blurb: "End-to-end features, auth, APIs and UI", focus: ["Next.js", "Node.js", "Auth & security", "Databases", "Real-time"] },
  { key: "mobile", full: "Mobile Engineer", title: "Mobile", blurb: "iOS / Android, offline sync, app performance", focus: ["Swift / Kotlin", "React Native", "Offline-first", "App lifecycle", "Performance"] },
  { key: "data", full: "Data Engineer", title: "Data Engineering", blurb: "Pipelines, warehousing, streaming, data quality", focus: ["Spark", "Airflow", "Data modeling", "Streaming", "SQL"] },
  { key: "ml", full: "Machine Learning Engineer", title: "Machine Learning", blurb: "Modeling, evaluation, MLOps, LLM systems", focus: ["Model evaluation", "MLOps", "LLMs & RAG", "Feature engineering", "Deep learning"] },
  { key: "devops", full: "DevOps / SRE Engineer", title: "DevOps / SRE", blurb: "Cloud, Kubernetes, CI/CD, reliability", focus: ["Kubernetes", "AWS", "Observability", "Incident response", "Terraform"] },
  { key: "security", full: "Security Engineer", title: "Security", blurb: "AppSec, threat modeling, cloud security", focus: ["OWASP Top 10", "Threat modeling", "Cryptography", "Cloud security", "Incident response"] },
  { key: "custom", full: "", title: "Something else", blurb: "Type any tech role you're preparing for", focus: ["Fundamentals", "System design", "Problem solving", "Debugging"] },
];

export const LEVELS: { key: Level; title: string; years: string }[] = [
  { key: "intern", title: "Intern", years: "Student" },
  { key: "junior", title: "Junior", years: "0–2 yrs" },
  { key: "mid", title: "Mid-level", years: "2–5 yrs" },
  { key: "senior", title: "Senior", years: "5–8 yrs" },
  { key: "staff", title: "Staff+", years: "8+ yrs" },
];

export type Feedback = { score?: number; summary?: string; strengths?: string[]; improvements?: string[]; model_answer?: string[]; automated?: boolean };
export type CurrentQuestion = { position: number; question: string; category: string; category_label: string; intro: string | null; is_follow_up: boolean; number: number; total: number };
export type Turn = { id: number; position: number; question: string; category: string; category_label: string; is_follow_up: boolean; answer: string; feedback: string | null; score: number | null };
export type Integrity = { monitored: boolean; warnings: number; status: "clean" | "minor" | "flagged"; events: Record<string, { count: number; seconds: number }> };
export type Report = { overall_score: number; verdict: string; summary: string; competencies: { key: string; name: string; score: number; note: string }[]; strengths: string[]; improvements: string[]; next_steps?: string[]; integrity: Integrity; automated: boolean };
export type TechSession = {
  id: number; type: "tech"; status: string; created_at: string; voice_enabled: boolean;
  role: string; level: Level; level_label: string; mode: Mode; voice_only: boolean; proctored: boolean; focus: string;
  current_question: CurrentQuestion | null; answered_main: number; total_main: number; turns: Turn[]; report: Report | null; integrity: Integrity;
};
export type TurnResult = { feedback: Feedback | null; reaction: string; completed: boolean; closing: string | null };

export const QUESTION_SECONDS: Record<Mode, number> = { practice: 0, assessment: 180 };

export function scoreTone(score: number | null | undefined) {
  if (score == null) return "neutral";
  return score >= 8 ? "strong" : score >= 6 ? "good" : score >= 4 ? "fair" : "weak";
}
