"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabaseBrowserClient } from "@/lib/supabase";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    const { data, error } = await supabaseBrowserClient.auth.signInWithPassword({
      email,
      password,
    });
    if (error) {
      setError(error.message);
      setSubmitting(false);
      return;
    }

    const { data: employee } = await supabaseBrowserClient
      .from("employees")
      .select("id")
      .eq("auth_user_id", data.user.id)
      .single();

    const { data: trip } = employee
      ? await supabaseBrowserClient
          .from("trips")
          .select("id")
          .eq("employee_id", employee.id)
          .limit(1)
          .single()
      : { data: null };

    router.push(trip ? `/chat/${trip.id}` : "/itinerary");
  }

  return (
    <div className="flex min-h-dvh w-full flex-col items-center justify-center bg-[var(--color-paper)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="font-display text-2xl font-bold tracking-tight text-[var(--color-ink)]">
            Wayfare
          </span>
          <p className="mt-1 font-sans text-sm text-[var(--color-slate)]">
            Sign in to book and manage company travel.
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 rounded-lg border border-black/5 bg-white p-6 shadow-[0_1px_3px_rgba(27,42,65,0.08)]"
        >
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="email"
              className="font-mono text-xs uppercase tracking-wide text-[var(--color-slate)]"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="rounded-md border border-black/10 bg-white px-3 py-2 font-sans text-sm text-[var(--color-ink)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-amber)]"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="password"
              className="font-mono text-xs uppercase tracking-wide text-[var(--color-slate)]"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="rounded-md border border-black/10 bg-white px-3 py-2 font-sans text-sm text-[var(--color-ink)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-amber)]"
            />
          </div>

          {error && (
            <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="mt-2 rounded-md bg-[var(--color-amber)] px-4 py-2 font-sans text-sm font-semibold text-[var(--color-ink)] outline-none transition-opacity focus-visible:ring-2 focus-visible:ring-[var(--color-amber)] focus-visible:ring-offset-2 disabled:opacity-60"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
