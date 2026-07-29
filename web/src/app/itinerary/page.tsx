"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { AppShell } from "@/components/app-shell";
import { BookingCard, type Booking, type BookingStatus } from "@/components/booking-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

// Raw booking row as returned by GET /trips/{trip_id}/bookings (Task 8).
type BookingRow = {
  id: string;
  trip_id: string;
  kind: "flight" | "hotel";
  details: Record<string, unknown>;
  price_cents: number;
  status: BookingStatus;
};

// Sort key: pending_approval first (needs action), then booked, then rejected.
const STATUS_ORDER: Record<BookingStatus, number> = {
  pending_approval: 0,
  booked: 1,
  rejected: 2,
};

const FILTERS = {
  pending: { label: "Pending", match: (s: BookingStatus) => s === "pending_approval" },
  booked: { label: "Booked", match: (s: BookingStatus) => s === "booked" },
  all: { label: "All", match: () => true },
} as const;

type FilterKey = keyof typeof FILTERS;

// Flatten the DB row (nested `details`) into the shape BookingCard renders.
// `details` already matches FlightOption/HotelOption, so spreading it supplies
// airline/origin/... (or name/location/...); we override id/status from the row.
function toBooking(row: BookingRow): Booking {
  return {
    ...(row.details as object),
    kind: row.kind,
    id: row.id,
    status: row.status,
  } as Booking;
}

function money(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function summarize(booking: Booking): string {
  return booking.kind === "flight"
    ? `${booking.origin} → ${booking.destination} · ${booking.fare_class}`
    : `${booking.name} · ${booking.location}`;
}

const STATUS_BADGE = {
  booked: { tone: "confirmed", text: "✓ CONFIRMED" },
  pending_approval: { tone: "pending", text: "⏳ PENDING" },
  rejected: { tone: "rejected", text: "✕ REJECTED" },
} as const;

export default function ItineraryPage() {
  const [rows, setRows] = useState<BookingRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Bumping this re-runs the load effect (used to refetch after approve/reject
  // without a full page reload).
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let active = true;
    (async () => {
      const {
        data: { user },
      } = await supabaseBrowserClient.auth.getUser();
      if (!active) return;
      if (!user) {
        setError("Sign in to view your trips.");
        setLoading(false);
        return;
      }
      setError(null);

      // employee -> trips -> bookings. auth_user_id links the Supabase auth
      // user to the employees row (see supabase/migrations init).
      const { data: employee, error: empErr } = await supabaseBrowserClient
        .from("employees")
        .select("id")
        .eq("auth_user_id", user.id)
        .maybeSingle();
      if (!active) return;
      if (empErr) {
        setError(empErr.message);
        setLoading(false);
        return;
      }
      if (!employee) {
        setRows([]);
        setLoading(false);
        return;
      }

      const { data: trips, error: tripErr } = await supabaseBrowserClient
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
        const perTrip = await Promise.all(
          (trips ?? []).map(async (t) => {
            const res = await fetch(`${API_BASE}/trips/${t.id}/bookings`);
            if (!res.ok)
              throw new Error(`Failed to load bookings (${res.status})`);
            return (await res.json()) as BookingRow[];
          }),
        );
        if (!active) return;
        const all = perTrip.flat();
        all.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
        setRows(all);
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
  }, [reloadKey]);

  const act = useCallback(async (id: string, action: "approve" | "reject") => {
    try {
      const res = await fetch(`${API_BASE}/bookings/${id}/${action}`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Action failed (${res.status})`);
      setError(null);
      setReloadKey((k) => k + 1); // refetch: status + actions update in place
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }, []);

  const visible = useMemo(
    () => rows.filter((r) => FILTERS[filter].match(r.status)),
    [rows, filter],
  );

  const pendingCount = rows.filter(
    (r) => r.status === "pending_approval",
  ).length;

  // Keep a valid selection as the filter narrows the queue.
  const selected =
    visible.find((r) => r.id === selectedId) ?? visible[0] ?? null;

  return (
    <AppShell
      title="Trips"
      meta={
        loading
          ? "Loading…"
          : `${rows.length} total · ${pendingCount} awaiting approval`
      }
      actions={
        <div className="flex gap-1 rounded-[9px] bg-[#f4f2ee] p-[3px]">
          {(Object.keys(FILTERS) as FilterKey[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              aria-pressed={filter === key}
              className={cn(
                "rounded-[7px] px-3.5 py-1.5 font-sans text-[13px] transition-colors duration-[var(--duration-quick)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none",
                filter === key
                  ? "bg-white font-semibold text-[var(--color-ink)] shadow-[0_1px_2px_rgba(27,42,65,0.08)]"
                  : "font-medium text-[var(--color-slate)] hover:text-[var(--color-ink)]",
              )}
            >
              {FILTERS[key].label}
              {key === "pending" && pendingCount > 0 && ` ${pendingCount}`}
            </button>
          ))}
        </div>
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

      <div className="grid min-h-0 flex-1 grid-cols-[340px_1fr]">
        {/* queue */}
        <div className="overflow-y-auto border-r border-[var(--color-line)] bg-[#fbfaf8] p-4">
          {loading && (
            <div className="flex flex-col gap-2.5">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-[92px] animate-pulse rounded-xl bg-[rgba(27,42,65,0.05)]"
                />
              ))}
            </div>
          )}

          {!loading && visible.length === 0 && (
            <p className="px-1 py-6 font-sans text-sm text-[var(--color-slate)]">
              {filter === "pending"
                ? "Nothing waiting on you. Approved and booked trips stay under Booked."
                : "No trips here yet. Start one in chat and it lands on this list."}
            </p>
          )}

          <div className="flex flex-col gap-2.5">
            {visible.map((row) => {
              const booking = toBooking(row);
              const isSelected = selected?.id === row.id;
              return (
                <button
                  key={row.id}
                  type="button"
                  onClick={() => setSelectedId(row.id)}
                  aria-current={isSelected ? "true" : undefined}
                  className={cn(
                    "animate-[var(--animate-rise-in)] rounded-xl bg-white p-3.5 text-left transition-[border-color,box-shadow] duration-[var(--duration-quick)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none",
                    isSelected
                      ? "border-[1.5px] border-[var(--color-ink)]"
                      : "border border-[rgba(27,42,65,0.1)] hover:border-[rgba(27,42,65,0.25)]",
                  )}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-sans text-[15px] font-semibold text-[var(--color-ink)]">
                      {booking.kind === "flight" ? booking.airline : booking.name}
                    </span>
                    <Badge tone={STATUS_BADGE[row.status].tone}>
                      {STATUS_BADGE[row.status].text}
                    </Badge>
                  </div>
                  <p className="mt-1 font-mono text-xs text-[var(--color-slate)]">
                    {summarize(booking)}
                  </p>
                  <p className="mt-2 font-mono text-xs text-[var(--color-ink)]">
                    {money(row.price_cents)}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* detail */}
        <div className="overflow-y-auto p-7">
          {selected ? (
            <div key={selected.id} className="animate-[var(--animate-rise-in)]">
              <div className="mb-5 flex items-center gap-3">
                <div>
                  <h2 className="font-display text-lg font-semibold text-[var(--color-ink)]">
                    {selected.kind === "flight" ? "Flight" : "Hotel"} ·{" "}
                    {money(selected.price_cents)}
                  </h2>
                  <p className="font-mono text-xs text-[var(--color-slate)]">
                    TRIP {selected.trip_id.slice(0, 8)}
                  </p>
                </div>
                <Badge
                  tone={STATUS_BADGE[selected.status].tone}
                  className="ml-auto"
                >
                  {STATUS_BADGE[selected.status].text}
                </Badge>
              </div>

              <div className="mb-5 max-w-[560px]">
                <BookingCard booking={toBooking(selected)} />
              </div>

              {selected.status === "pending_approval" ? (
                <div className="flex items-center gap-3">
                  <Button
                    variant="confirm"
                    onClick={() => act(selected.id, "approve")}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => act(selected.id, "reject")}
                  >
                    Reject
                  </Button>
                  <span className="ml-auto font-sans text-xs text-[var(--color-mute)]">
                    The traveler is notified either way.
                  </span>
                </div>
              ) : (
                <p className="font-sans text-sm text-[var(--color-slate)]">
                  {selected.status === "booked"
                    ? "Booked and confirmed. Nothing left to do."
                    : "This request was rejected."}
                </p>
              )}
            </div>
          ) : (
            !loading && (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
                <p className="font-display text-lg font-semibold text-[var(--color-ink)]">
                  Nothing selected
                </p>
                <p className="max-w-[320px] font-sans text-sm text-[var(--color-slate)]">
                  Pick a trip from the queue to review its details.
                </p>
              </div>
            )
          )}
        </div>
      </div>
    </AppShell>
  );
}
