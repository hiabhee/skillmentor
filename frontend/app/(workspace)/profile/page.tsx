"use client";

import { FormEvent, useState } from "react";
import useSWR from "swr";
import { Check, Save, UserRound } from "lucide-react";
import { api } from "@/lib/api";

type User = { id: number; name: string; email: string; bio: string };
export default function ProfilePage() {
  const { data, mutate } = useSWR<{ user: User }>("/auth/me", (path: string) => api<{ user: User }>(path));
  const [notice, setNotice] = useState(""); const [error, setError] = useState(""); const [pending, setPending] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setPending(true); setError(""); setNotice(""); const form = new FormData(event.currentTarget); try { const updated = await api<{ user: User }>("/profile", { method: "PUT", body: JSON.stringify({ name: form.get("name"), bio: form.get("bio") }) }); await mutate(updated); setNotice("Your profile has been saved."); } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save your profile."); } finally { setPending(false); } }
  return <><div className="page-heading"><div><span className="eyebrow">ACCOUNT SETTINGS</span><h1>Your profile.</h1><p>Keep the details used in your workspace up to date.</p></div></div><section className="panel profile-panel"><div className="profile-identity"><span className="profile-avatar"><UserRound size={25} /></span><div><span className="eyebrow">MEMBER PROFILE</span><h2>{data?.user.name || "Your name"}</h2><p>{data?.user.email}</p></div></div><form onSubmit={save} className="profile-form"><label className="field-label">Full name<input name="name" defaultValue={data?.user.name} key={data?.user.name} required maxLength={160} /></label><label className="field-label">Email address<input value={data?.user.email || ""} readOnly disabled /></label><label className="field-label">A little about you <span className="optional">OPTIONAL</span><textarea name="bio" defaultValue={data?.user.bio} key={`bio-${data?.user.id}`} rows={4} maxLength={1000} placeholder="Your role, focus area, or a goal you’re working toward." /></label>{notice && <div className="notice success-notice"><Check size={15} />{notice}</div>}{error && <div className="notice error-notice">{error}</div>}<div className="form-actions"><span>Your practice history belongs to your account.</span><button className="button primary" disabled={pending}>{pending ? "Saving…" : "Save changes"}<Save size={15} /></button></div></form></section></>;
}
