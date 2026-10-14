"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, LoaderCircle, Sparkles } from "lucide-react";
import { api } from "@/lib/api";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [pending, setPending] = useState<"submit" | "demo" | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setPending("submit");
    const form = new FormData(event.currentTarget);
    try {
      await api(`/auth/${mode === "register" ? "register" : "login"}`, { method: "POST", body: JSON.stringify({ name: form.get("name"), email: form.get("email"), password: form.get("password") }) });
      router.replace("/"); router.refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to sign in. Try again."); }
    finally { setPending(null); }
  }
  async function openDemo() {
    setError(""); setPending("demo");
    try {
      await api("/auth/demo", { method: "POST", body: JSON.stringify({}) });
      router.replace("/"); router.refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The demo workspace could not be opened."); }
    finally { setPending(null); }
  }
  return <div className="auth-card">
    <span className="eyebrow">{mode === "register" ? "GET STARTED" : "WELCOME BACK"}</span>
    <h2>{mode === "register" ? "Create your account" : "Sign in to your workspace"}</h2>
    <p className="auth-lede">{mode === "register" ? "A few focused minutes can change how you show up." : "Pick up where your preparation left off."}</p>
    <form onSubmit={submit} className="form-stack">
      {mode === "register" && <label className="field-label">Full name<input name="name" autoComplete="name" placeholder="Alex Morgan" required maxLength={120} /></label>}
      <label className="field-label">Email address<input type="email" name="email" autoComplete="email" placeholder="you@company.com" required maxLength={320} /></label>
      <label className="field-label">Password<input type="password" name="password" autoComplete={mode === "register" ? "new-password" : "current-password"} placeholder={mode === "register" ? "At least 12 characters" : "Your password"} required minLength={mode === "register" ? 12 : undefined} maxLength={128} /></label>
      {error && <div className="notice error-notice" role="alert">{error}</div>}
      <button className="button primary full-button" type="submit" disabled={pending !== null}>{pending === "submit" ? <LoaderCircle className="spin" size={17} /> : <>{mode === "register" ? "Create account" : "Sign in"}<ArrowRight size={16} /></>}</button>
    </form>
    {mode === "login" && <div className="auth-demo"><div className="auth-demo-divider"><span>OR EXPLORE A SAMPLE</span></div><button className="button secondary full-button" type="button" onClick={openDemo} disabled={pending !== null}>{pending === "demo" ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}{pending === "demo" ? "Opening demo workspace…" : "Explore the demo account"}</button><p>Sample sessions, feedback, and progress. Changes are shared with demo visitors.</p></div>}
    <p className="auth-switch">{mode === "register" ? "Already have an account?" : "New to Skillmentor?"} <Link href={mode === "register" ? "/login" : "/register"}>{mode === "register" ? "Sign in" : "Create an account"}</Link></p>
    <p className="auth-terms">By continuing, you agree to use your feedback as a learning guide. AI feedback can be imperfect.</p>
  </div>;
}
