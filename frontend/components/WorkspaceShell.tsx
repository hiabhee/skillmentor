"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import useSWR from "swr";
import { BarChart3, BookOpenCheck, ChevronDown, CircleHelp, Clock3, LayoutDashboard, LogOut, Sparkles, UserRound } from "lucide-react";
import { api } from "@/lib/api";

type User = { id: number; name: string; email: string; bio: string };
const nav = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/practice", label: "Practice", icon: BookOpenCheck },
  { href: "/history", label: "History", icon: Clock3 },
  { href: "/analytics", label: "Progress", icon: BarChart3 },
  { href: "/achievements", label: "Achievements", icon: Sparkles },
];

export default function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { data, error, isLoading } = useSWR<{ user: User }>("/auth/me", (path: string) => api(path), { shouldRetryOnError: false });
  useEffect(() => {
    if (!isLoading && (error || !data?.user)) router.replace("/login");
  }, [data, error, isLoading, router]);

  async function signOut() {
    try { await api("/auth/logout", { method: "POST" }); } finally { router.replace("/login"); }
  }

  if (isLoading || !data?.user) return <main className="boot-screen"><span className="brand-mark"><Sparkles size={16} /></span><p>Opening your workspace…</p></main>;
  const user = data.user;
  return <div className="workspace">
    <aside className="sidebar">
      <Link className="brand" href="/"><span className="brand-mark"><Sparkles size={17} /></span><span>Skillmentor<small>INTERVIEW STUDIO</small></span></Link>
      <div className="side-caption">WORKSPACE</div>
      <nav className="primary-nav" aria-label="Main navigation">
        {nav.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className={`nav-link ${pathname === href || (href !== "/" && pathname.startsWith(href)) ? "active" : ""}`}><Icon size={17} strokeWidth={1.8} /><span>{label}</span>{href === "/practice" && <ChevronDown className="nav-chevron" size={14} />}</Link>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="side-caption">YOUR ACCOUNT</div>
        <Link className={`nav-link ${pathname === "/profile" ? "active" : ""}`} href="/profile"><UserRound size={17} strokeWidth={1.8} /><span>Profile</span></Link>
        <div className="sidebar-help"><CircleHelp size={17} /><div><strong>Need a hand?</strong><span>Practice at your own pace.</span></div></div>
        <button className="account-chip" onClick={signOut} aria-label="Sign out"><span className="avatar">{user.name.charAt(0).toUpperCase()}</span><span className="account-copy"><strong>{user.name}</strong><small>{user.email}</small></span><LogOut size={15} /></button>
      </div>
    </aside>
    <main className="main-area"><header className="topbar"><div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><strong>{nav.find((item) => pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href)))?.label || (pathname.startsWith("/sessions") ? "Interview" : "Profile")}</strong></div><div className="topbar-right"><span className="secure-label"><span className="status-dot" /> Your practice, saved</span><span className="avatar avatar-small">{user.name.charAt(0).toUpperCase()}</span></div></header><div className="page-content">{children}</div></main>
  </div>;
}
