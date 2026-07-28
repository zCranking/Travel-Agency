"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type RiskLevel = "low" | "medium" | "high";

type DutyOfCareRow = {
  employee_id: string;
  name: string;
  trip: {
    trip_id: string;
    destination: string;
    risk_level: RiskLevel;
    bookings: { id: string; kind: "flight" | "hotel"; details: Record<string, unknown>; status: string }[];
  } | null;
};

const RISK_STYLES: Record<RiskLevel, string> = {
  low: "bg-[var(--color-teal)]",
  medium: "bg-[var(--color-amber)]",
  high: "bg-[var(--color-coral)]",
};

const RISK_TEXT: Record<RiskLevel, string> = {
  low: "text-white",
  medium: "text-[var(--color-ink)]",
  high: "text-white",
};

const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

export default function DutyOfCarePage() {
  const [rows, setRows] = useState<DutyOfCareRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/duty-of-care`);
        if (!res.ok) throw new Error(`Failed to load (${res.status})`);
        const data = (await res.json()) as DutyOfCareRow[];
        if (active) setRows(data);
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Something went wrong.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[640px] flex-col bg-white">
      <header className="flex items-baseline justify-between bg-[var(--color-ink)] px-4 py-3 text-white">
        <span className="font-display text-lg font-bold tracking-tight">Wayfare</span>
        <span className="font-mono text-xs text-white/60">Duty of Care</span>
      </header>

      <main className="flex flex-1 flex-col gap-3 p-4">
        {error && (
          <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
            {error}
          </p>
        )}

        {!loading && !error && rows.length === 0 && (
          <p className="font-sans text-sm text-[var(--color-slate)]">No employees found.</p>
        )}

        {rows.map((row) => (
          <div
            key={row.employee_id}
            className="flex items-center justify-between rounded-lg border border-black/5 bg-white p-4 shadow-[0_1px_3px_rgba(27,42,65,0.08)]"
          >
            <div>
              <p className="font-sans text-sm font-semibold text-[var(--color-ink)]">{row.name}</p>
              {row.trip ? (
                <p className="font-mono text-xs text-[var(--color-slate)]">{row.trip.destination}</p>
              ) : (
                <p className="font-mono text-xs text-[var(--color-slate)]">No active trip</p>
              )}
            </div>

            {row.trip && (
              <div className="flex flex-col items-end gap-0.5">
                <span
                  className={`rounded-full px-2.5 py-0.5 font-sans text-xs font-semibold ${RISK_STYLES[row.trip.risk_level]} ${RISK_TEXT[row.trip.risk_level]}`}
                >
                  {RISK_LABELS[row.trip.risk_level]}
                </span>
                <span className="font-mono text-[10px] text-[var(--color-slate)]">
                  (placeholder data)
                </span>
              </div>
            )}
          </div>
        ))}
      </main>
    </div>
  );
}
