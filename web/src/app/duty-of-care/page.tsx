"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { RiskLabel } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type RiskLevel = "low" | "medium" | "high";

type DutyOfCareRow = {
  employee_id: string;
  name: string;
  trip: {
    trip_id: string;
    destination: string;
    risk_level: RiskLevel;
    bookings: {
      id: string;
      kind: "flight" | "hotel";
      details: Record<string, unknown>;
      status: string;
    }[];
  } | null;
};

const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

const RISK_ORDER: Record<RiskLevel, number> = { high: 0, medium: 1, low: 2 };

const AVATAR_BG: Record<RiskLevel, string> = {
  low: "bg-[var(--color-teal)] text-white",
  medium: "bg-[var(--color-amber)] text-[var(--color-ink)]",
  high: "bg-[var(--color-coral)] text-white",
};

function initials(name: string): string {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

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
        if (active)
          setError(e instanceof Error ? e.message : "Something went wrong.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const traveling = rows.filter((r) => r.trip !== null);
  const counts = {
    low: traveling.filter((r) => r.trip!.risk_level === "low").length,
    medium: traveling.filter((r) => r.trip!.risk_level === "medium").length,
    high: traveling.filter((r) => r.trip!.risk_level === "high").length,
  };
  const destinations = new Set(traveling.map((r) => r.trip!.destination));
  const atRisk = traveling
    .filter((r) => r.trip!.risk_level === "high")
    .sort((a, b) => a.name.localeCompare(b.name));

  const sorted = [...rows].sort((a, b) => {
    if (!a.trip) return 1;
    if (!b.trip) return -1;
    const byRisk =
      RISK_ORDER[a.trip.risk_level] - RISK_ORDER[b.trip.risk_level];
    return byRisk !== 0 ? byRisk : a.name.localeCompare(b.name);
  });

  return (
    <AppShell
      title="Duty of care"
      meta={
        loading
          ? "Loading…"
          : `${traveling.length} traveling · ${destinations.size} destination${destinations.size === 1 ? "" : "s"}`
      }
      actions={
        !loading && traveling.length > 0 ? (
          <div className="flex gap-5">
            {(["low", "medium", "high"] as const).map((level) => (
              <div key={level} className="text-right">
                <div className="font-mono text-[10px] uppercase text-[var(--color-mute)]">
                  {RISK_LABELS[level]}
                </div>
                <div
                  className={cn(
                    "font-display text-lg font-bold",
                    level === "low" && "text-[var(--color-teal)]",
                    level === "medium" && "text-[var(--color-amber-ink)]",
                    level === "high" && "text-[var(--color-coral)]",
                  )}
                >
                  {counts[level]}
                </div>
              </div>
            ))}
          </div>
        ) : undefined
      }
    >
      {error && (
        <p
          role="alert"
          className="flex items-center gap-2.5 border-b border-[rgba(193,84,60,0.2)] bg-[rgba(193,84,60,0.08)] px-7 py-3 font-sans text-sm text-[var(--color-ink)]"
        >
          <span aria-hidden className="font-semibold text-[var(--color-coral)]">
            !
          </span>
          {error}
        </p>
      )}

      {atRisk.length > 0 && (
        <div className="flex items-center gap-3 border-b border-[rgba(193,84,60,0.2)] bg-[rgba(193,84,60,0.08)] px-7 py-3">
          <span
            aria-hidden
            className="size-2 flex-none rounded-full bg-[var(--color-coral)]"
          />
          <p className="font-sans text-[13px] text-[var(--color-ink)]">
            <b>High risk · {atRisk.length} traveler{atRisk.length === 1 ? "" : "s"}</b>{" "}
            — {atRisk.map((r) => r.name).join(", ")} in a high-risk destination.
          </p>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
        {loading && (
          <div className="grid max-w-[900px] grid-cols-2 gap-3">
            {[0, 1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-[76px] animate-pulse rounded-xl bg-[rgba(27,42,65,0.05)]"
              />
            ))}
          </div>
        )}

        {!loading && !error && rows.length === 0 && (
          <div className="flex flex-col items-start gap-2">
            <p className="font-display text-lg font-semibold text-[var(--color-ink)]">
              No travelers yet
            </p>
            <p className="max-w-[380px] font-sans text-sm text-[var(--color-slate)]">
              Once trips are booked, everyone on the road shows up here with
              their destination and risk level.
            </p>
          </div>
        )}

        <div className="grid max-w-[900px] grid-cols-2 gap-3">
          {sorted.map((row) => (
            <div
              key={row.employee_id}
              className={cn(
                "animate-[var(--animate-rise-in)] rounded-xl border bg-white p-3.5",
                row.trip?.risk_level === "high"
                  ? "border-[rgba(193,84,60,0.3)]"
                  : "border-[rgba(27,42,65,0.1)]",
              )}
            >
              <div className="flex items-center gap-3">
                <span
                  aria-hidden
                  className={cn(
                    "flex size-9 flex-none items-center justify-center rounded-full font-sans text-[13px] font-semibold",
                    row.trip
                      ? AVATAR_BG[row.trip.risk_level]
                      : "bg-[#e8e4dc] text-[var(--color-slate)]",
                  )}
                >
                  {initials(row.name)}
                </span>
                <div className="min-w-0 flex-1 leading-tight">
                  <p className="truncate font-sans text-sm font-semibold text-[var(--color-ink)]">
                    {row.name}
                  </p>
                  <p className="truncate font-mono text-[11px] text-[var(--color-slate)]">
                    {row.trip ? row.trip.destination : "Not traveling"}
                  </p>
                </div>
                {row.trip && (
                  <RiskLabel level={row.trip.risk_level}>
                    {RISK_LABELS[row.trip.risk_level].toUpperCase()}
                  </RiskLabel>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
