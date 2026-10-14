import Link from "next/link";

export default function NotFound() { return <main className="not-found"><span className="eyebrow">404 · PAGE NOT FOUND</span><h1>Looks like this path is closed.</h1><p>The page may have moved. Head back to your workspace to continue.</p><Link className="button primary" href="/">Return to workspace</Link></main>; }
