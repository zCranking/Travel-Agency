"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabaseBrowserClient } from "@/lib/supabase";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

const LABEL =
  "font-mono text-[11px] uppercase tracking-wide text-(--color-slate)";
const INPUT =
  "rounded-lg border border-(--color-line) px-3 py-2 font-sans text-sm text-(--color-ink) focus-visible:border-(--color-teal) focus-visible:ring-2 focus-visible:ring-(--color-teal) focus-visible:outline-none";

export default function PlanStartPage() {
  const router = useRouter();
  const [employeeId, setEmployeeId] = useState<string | null>(null);
  const [origin, setOrigin] = useState("SFO");
  const [budget, setBudget] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      const {
        data: { user },
      } = await supabaseBrowserClient.auth.getUser();
      if (!active) return;
      if (!user) {
        setError("Sign in to plan a trip.");
        return;
      }
      const { data: employee, error: empErr } = await supabaseBrowserClient
        .from("employees")
        .select("id")
        .eq("auth_user_id", user.id)
        .maybeSingle();
      if (!active) return;
      if (empErr) {
        setError(empErr.message);
        return;
      }
      if (!employee) {
        setError("No employee record for this account.");
        return;
      }
      setEmployeeId(employee.id as string);
    })();
    return () => {
      active = false;
    };
  }, []);

  async function start() {
    if (!employeeId) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/trips`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          employee_id: employeeId,
          origin_city: origin.trim().toUpperCase(),
          // Dollars in, integer cents out — money is cents everywhere behind here.
          budget_cents: budget ? Math.round(Number(budget) * 100) : null,
        }),
      });
      if (!res.ok) throw new Error(`Could not start a trip (${res.status})`);
      const { id } = (await res.json()) as { id: string };
      router.push(`/plan/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setCreating(false);
    }
  }

  return (
    <AppShell title="Plan a trip" meta="Start with where you have to be">
      <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
        <div className="max-w-[560px]">
          {error && (
            <p
              role="alert"
              className="mb-5 flex items-center gap-2.5 rounded-xl border border-[rgba(193,84,60,0.35)] border-l-[3px] border-l-(--color-coral) bg-white px-4 py-3 font-sans text-sm text-(--color-ink)"
            >
              <span aria-hidden className="font-semibold text-(--color-coral)">
                !
              </span>
              {error}
            </p>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              start();
            }}
            className="rounded-xl border border-(--color-line) bg-white p-5"
          >
            <p className="mb-4 font-sans text-sm text-(--color-slate)">
              Tell us where you start from. Next you list the meetings you have
              to make, and we work out which itineraries actually make them.
            </p>

            <div className="flex flex-wrap items-end gap-4">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="origin" className={LABEL}>
                  Home airport (IATA)
                </label>
                <input
                  id="origin"
                  value={origin}
                  maxLength={3}
                  onChange={(e) => setOrigin(e.target.value.toUpperCase())}
                  className={`${INPUT} w-24 font-mono uppercase`}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="budget" className={LABEL}>
                  Trip budget ($, optional)
                </label>
                <input
                  id="budget"
                  type="number"
                  min="0"
                  step="1"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  placeholder="1200"
                  className={`${INPUT} w-36 font-mono`}
                />
              </div>

              <Button
                type="submit"
                disabled={!employeeId || creating || origin.trim().length < 3}
              >
                {creating ? "Starting…" : "Start planning"}
              </Button>
            </div>

            <p className="mt-4 font-sans text-xs text-(--color-mute)">
              Over budget is a flagged plan, never a hidden one.
            </p>
          </form>
        </div>
      </div>
    </AppShell>
  );
}
