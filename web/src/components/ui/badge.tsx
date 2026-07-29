import { cn } from "@/lib/utils";

const TONES = {
  inPolicy: "bg-[rgba(47,110,99,0.12)] text-[var(--color-teal)]",
  outOfPolicy: "bg-[rgba(193,84,60,0.12)] text-[var(--color-coral)]",
  confirmed: "bg-[var(--color-teal)] text-white",
  pending: "bg-[rgba(232,163,61,0.18)] text-[var(--color-amber-ink)]",
  rejected: "bg-[rgba(27,42,65,0.08)] text-[var(--color-slate)]",
  onInk: "bg-white/12 text-white",
} as const;

export type BadgeTone = keyof typeof TONES;

export function Badge({
  tone = "inPolicy",
  className,
  children,
}: {
  tone?: BadgeTone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[11px] font-semibold",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const RISK_DOT = {
  low: "bg-[var(--color-teal)]",
  medium: "bg-[var(--color-amber)]",
  high: "bg-[var(--color-coral)]",
} as const;

const RISK_TEXT = {
  low: "text-[var(--color-teal)]",
  medium: "text-[var(--color-amber-ink)]",
  high: "text-[var(--color-coral)]",
} as const;

/**
 * Risk is never signalled by colour alone — the dot always ships with its label.
 */
export function RiskLabel({
  level,
  children,
}: {
  level: keyof typeof RISK_DOT;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold",
        RISK_TEXT[level],
      )}
    >
      <span
        aria-hidden
        className={cn("size-2.5 rounded-full", RISK_DOT[level])}
      />
      {children}
    </span>
  );
}
