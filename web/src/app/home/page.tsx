"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import type {
  Booking,
  BookingStatus,
  FlightBooking,
  HotelBooking,
} from "@/components/booking-card";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

type BookingRow = {
  id: string;
  trip_id: string;
  kind: "flight" | "hotel";
  details: Record<string, unknown>;
  price_cents: number;
  status: BookingStatus;
};

type Trip = {
  id: string;
  bookings: Booking[];
  flight?: FlightBooking;
  hotel?: HotelBooking;
  departsAt?: Date;
  status: BookingStatus;
};

function toBooking(row: BookingRow): Booking {
  return {
    ...(row.details as object),
    kind: row.kind,
    id: row.id,
    status: row.status,
  } as Booking;
}

// A trip reads as pending if anything in it still needs a decision.
function tripStatus(bookings: Booking[]): BookingStatus {
  if (bookings.some((b) => b.status === "pending_approval"))
    return "pending_approval";
  if (bookings.some((b) => b.status === "booked")) return "booked";
  return "rejected";
}

const STAMP = {
  booked: { mark: "✓", label: "BKD", bg: "bg-[var(--color-teal)] text-white" },
  pending_approval: {
    mark: "…",
    label: "PEND",
    bg: "bg-[var(--color-coral)] text-white",
  },
  rejected: {
    mark: "✕",
    label: "REJ",
    bg: "bg-[var(--color-slate)] text-white",
  },
} as const;

function greeting(hour: number): string {
  if (hour < 12) return "good morning";
  if (hour < 18) return "good afternoon";
  return "good evening";
}

function daysUntil(date: Date): number {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(date);
  target.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

function countdown(date: Date): string {
  const days = daysUntil(date);
  if (days < 0) return "under way";
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

function formatDay(date: Date): string {
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function HomePage() {
  const [firstName, setFirstName] = useState<string | null>(null);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      const {
        data: { user },
      } = await supabaseBrowserClient.auth.getUser();
      if (!active) return;
      if (!user) {
        setError("Sign in to see your trips.");
        setLoading(false);
        return;
      }

      const { data: employee, error: empErr } = await supabaseBrowserClient
        .from("employees")
        .select("id, name")
        .eq("auth_user_id", user.id)
        .maybeSingle();
      if (!active) return;
      if (empErr) {
        setError(empErr.message);
        setLoading(false);
        return;
      }
      if (!employee) {
        setLoading(false);
        return;
      }
      setFirstName((employee.name as string).split(" ")[0]);

      const { data: tripRows, error: tripErr } = await supabaseBrowserClient
        .from("trips")
        .select("id")
        .eq("employee_id", employee.id);
      if (!active) return;
      if (tripErr) {
        setError(tripErr.message);
        setLoading(false);
        return;
      }

      try {
        const grouped = await Promise.all(
          (tripRows ?? []).map(async (t) => {
            const res = await fetch(`${API_BASE}/trips/${t.id}/bookings`);
            if (!res.ok) throw new Error(`Failed to load trips (${res.status})`);
            const bookings = ((await res.json()) as BookingRow[]).map(toBooking);
            const flight = bookings.find(
              (b): b is FlightBooking => b.kind === "flight",
            );
            const hotel = bookings.find(
              (b): b is HotelBooking => b.kind === "hotel",
            );
            const departsAt = flight ? new Date(flight.depart_date) : undefined;
            return {
              id: t.id as string,
              bookings,
              flight,
              hotel,
              departsAt:
                departsAt && !Number.isNaN(departsAt.getTime())
                  ? departsAt
                  : undefined,
              status: tripStatus(bookings),
            } satisfies Trip;
          }),
        );
        if (!active) return;
        grouped.sort(
          (a, b) =>
            (a.departsAt?.getTime() ?? Infinity) -
            (b.departsAt?.getTime() ?? Infinity),
        );
        setTrips(grouped.filter((t) => t.bookings.length > 0));
      } catch (e) {
        if (!active) return;
        setError(e instanceof Error ? e.message : "Something went wrong.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const next = trips.find((t) => t.departsAt && daysUntil(t.departsAt) >= 0);

  const now = new Date();

  const headline = next?.flight
    ? `${firstName ?? "Welcome back"}, you're off to ${next.flight.destination} ${countdown(next.departsAt!)}.`
    : firstName
      ? `${firstName}, nothing on the calendar yet.`
      : "Welcome to Wayfare.";

  return (
    <AppShell>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {/* hero — the design's ticket-stripe field stands in for the destination photo */}
        <div className="relative h-[300px] flex-none overflow-hidden bg-[repeating-linear-gradient(115deg,#233549,#233549_22px,#26394f_22px,#26394f_44px)]">
          <div
            aria-hidden
            className="absolute inset-0 bg-[linear-gradient(90deg,rgba(20,30,45,0.78)_0%,rgba(20,30,45,0.32)_62%,rgba(20,30,45,0.06)_100%)]"
          />
          <div className="absolute inset-x-8 top-5 flex items-center">
            <Link href="/itinerary">
              <span className="rounded-[10px] bg-[var(--color-amber)] px-[18px] py-2.5 font-sans text-sm font-semibold text-[var(--color-ink)] transition-[filter] duration-[var(--duration-quick)] hover:brightness-95">
                Review trips
              </span>
            </Link>
          </div>
          <div className="absolute inset-x-8 bottom-20 text-white">
            {/* Server and client clocks differ by timezone — the client's is correct. */}
            <p
              suppressHydrationWarning
              className="font-mono text-xs uppercase tracking-[0.06em] text-white/65"
            >
              {now
                ? `${now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })} · ${greeting(now.getHours())}`
                : " "}
            </p>
            <h1 className="mt-1.5 max-w-[760px] font-display text-[34px] font-bold leading-tight tracking-[-0.02em]">
              {loading ? " " : headline}
            </h1>
          </div>
        </div>

        <div className="px-8 pb-10">
          {/* next-trip pass, pulled up over the hero seam */}
          {next?.flight && (
            <div className="relative -mt-16 mb-6 flex animate-[var(--animate-rise-in)] overflow-hidden rounded-2xl bg-[var(--color-ink)] shadow-[0_18px_48px_rgba(27,42,65,0.28)]">
              <div className="flex-1 p-6 text-white">
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-[var(--color-amber)]">
                    Next trip · {countdown(next.departsAt!)}
                  </span>
                  <span className="font-mono text-[11px] text-white/50">
                    TRIP {next.id.slice(0, 8)}
                  </span>
                </div>

                <div className="mt-3.5 flex items-baseline gap-3.5">
                  <span className="font-display text-[34px] font-bold tracking-[-0.01em]">
                    {next.flight.origin}
                  </span>
                  <span aria-hidden className="text-white/50">
                    →
                  </span>
                  <span className="font-display text-[34px] font-bold tracking-[-0.01em]">
                    {next.flight.destination}
                  </span>
                  <span className="ml-3 font-sans text-sm text-white/75">
                    {formatDay(next.departsAt!)}
                  </span>
                </div>

                <div className="mt-4 flex gap-8">
                  <div>
                    <div className="font-mono text-[10px] tracking-[0.06em] text-white/50">
                      FLIGHT
                    </div>
                    <div className="font-sans text-[13px] font-medium">
                      {next.flight.airline} · {next.flight.fare_class}
                    </div>
                  </div>
                  {next.hotel && (
                    <div>
                      <div className="font-mono text-[10px] tracking-[0.06em] text-white/50">
                        HOTEL
                      </div>
                      <div className="font-sans text-[13px] font-medium">
                        {next.hotel.name}
                      </div>
                    </div>
                  )}
                  <div>
                    <div className="font-mono text-[10px] tracking-[0.06em] text-white/50">
                      DEPARTS
                    </div>
                    <div className="font-sans text-[13px] font-medium">
                      {countdown(next.departsAt!)}
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex gap-2">
                  <Badge
                    tone={next.status === "booked" ? "confirmed" : "pending"}
                  >
                    {next.status === "booked" ? "✓ CONFIRMED" : "⏳ PENDING"}
                  </Badge>
                  <Link
                    href="/itinerary"
                    className="rounded-full bg-white/12 px-3 py-1 font-mono text-[11px] font-medium text-white transition-colors duration-[var(--duration-quick)] hover:bg-white/20 focus-visible:ring-2 focus-visible:ring-[var(--color-amber)] focus-visible:outline-none"
                  >
                    Open itinerary →
                  </Link>
                </div>
              </div>
              <div
                aria-hidden
                className="w-[190px] flex-none border-l-2 border-dashed border-white/25 bg-[repeating-linear-gradient(135deg,#28394f,#28394f_12px,#2e415a_12px,#2e415a_24px)]"
              />
            </div>
          )}

          {error && (
            <p
              role="alert"
              className="mb-6 flex items-center gap-2.5 rounded-xl border border-[rgba(193,84,60,0.35)] border-l-[3px] border-l-[var(--color-coral)] bg-white px-4 py-3 font-sans text-sm text-[var(--color-ink)]"
            >
              <span
                aria-hidden
                className="font-semibold text-[var(--color-coral)]"
              >
                !
              </span>
              {error}
            </p>
          )}

          {/* ticket wall */}
          <div className="mb-3.5 flex items-baseline justify-between">
            <h2 className="font-display text-[17px] font-semibold tracking-[-0.01em] text-[var(--color-ink)]">
              Your trips
            </h2>
            <Link
              href="/itinerary"
              className="font-sans text-xs font-medium text-[var(--color-teal)] hover:underline"
            >
              View all →
            </Link>
          </div>

          {loading && (
            <div className="grid grid-cols-3 gap-4">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-[132px] animate-pulse rounded-2xl bg-[rgba(27,42,65,0.05)]"
                />
              ))}
            </div>
          )}

          {!loading && !error && trips.length === 0 && (
            <div className="rounded-2xl border border-[var(--color-line)] bg-white p-8">
              <p className="font-display text-lg font-semibold text-[var(--color-ink)]">
                No trips yet
              </p>
              <p className="mt-1 max-w-[420px] font-sans text-sm text-[var(--color-slate)]">
                Start a conversation and say where you need to be — Wayfare
                searches, checks it against policy, and books it.
              </p>
            </div>
          )}

          <div className="grid grid-cols-3 gap-4">
            {trips.map((trip) => {
              const stamp = STAMP[trip.status];
              return (
                <Link
                  key={trip.id}
                  href={`/chat/${trip.id}`}
                  className="flex animate-[var(--animate-rise-in)] overflow-hidden rounded-2xl border border-[rgba(27,42,65,0.09)] bg-white shadow-[0_6px_20px_rgba(27,42,65,0.08)] transition-[transform,box-shadow] duration-[var(--duration-quick)] ease-[var(--ease-standard)] hover:-translate-y-1 hover:shadow-[0_12px_28px_rgba(27,42,65,0.16)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none"
                >
                  <div className="flex-1 p-4">
                    <div className="font-mono text-[10px] font-medium tracking-[0.08em] text-[var(--color-amber-ink)]">
                      {trip.departsAt
                        ? `${formatDay(trip.departsAt).toUpperCase()} · ${countdown(trip.departsAt).toUpperCase()}`
                        : "NO DATE YET"}
                    </div>
                    <div className="mt-2 font-display text-xl font-bold text-[var(--color-ink)]">
                      {trip.flight?.destination ??
                        trip.hotel?.location ??
                        "Trip"}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-[var(--color-slate)]">
                      {trip.flight
                        ? `${trip.flight.origin} → ${trip.flight.destination}`
                        : (trip.hotel?.name ?? "—")}
                    </div>
                    <div className="mt-3.5 font-sans text-xs text-[var(--color-mute)]">
                      {trip.status === "pending_approval"
                        ? "Awaiting approval"
                        : trip.status === "booked"
                          ? `${trip.bookings.length} booked`
                          : "Rejected"}
                    </div>
                  </div>
                  <div className="flex items-center border-l-2 border-dashed border-[#d8d2c6]">
                    <div
                      className={`m-2 flex -rotate-2 flex-col items-center rounded-[5px] px-2 py-3 ${stamp.bg}`}
                    >
                      <span aria-hidden className="leading-none">
                        {stamp.mark}
                      </span>
                      <span className="font-mono text-[9px] font-semibold tracking-[0.06em]">
                        {stamp.label}
                      </span>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
