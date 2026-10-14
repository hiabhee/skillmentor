import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <main className="auth-page"><div className="auth-aside"><Link className="brand auth-brand" href="/"><span className="brand-mark">S</span><span>Skillmentor<small>INTERVIEW STUDIO</small></span></Link><div className="auth-message"><span className="eyebrow">A calmer way to prepare</span><h1>Show up ready<br />for what’s next.</h1><p>Practice with intention. Learn from each answer. Build confidence one session at a time.</p><div className="quote-card"><div className="quote-stars">★★★★★</div><p>“The feedback helped me see exactly where to add more detail and make my impact clear.”</p><span>— Product manager, recent member</span></div></div><span className="auth-footnote">Thoughtful practice. Measurable progress.</span></div><section className="auth-main">{children}</section></main>;
}
