import type { CSSProperties } from "react";
import type { CallPhase } from "./useVoiceCall";

/** Alex, the interviewer: a living orb that breathes, speaks, listens to your voice level, and thinks. */
export function InterviewerOrb({ phase, level, size }: { phase: CallPhase; level: number; size: "small" | "large" | "hero" }) {
  const style = { "--level": phase === "listening" ? level.toFixed(3) : "0" } as CSSProperties;
  return <div className={`orb orb-${size} orb-${phase}`} style={style} aria-hidden="true">
    <span className="orb-ring ring-1" /><span className="orb-ring ring-2" /><span className="orb-ring ring-3" />
    <span className="orb-core"><span className="orb-face"><i /><i /></span></span>
  </div>;
}
