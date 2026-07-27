"use client";

import { useCallback, useEffect, useState } from "react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { BookingCard, type Booking, type BookingStatus } from "@/components/booking-card";

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

export default function ItineraryPage() {
  const [rows, setRows] = useState<BookingRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
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
        setError("Please sign in to view your itinerary.");
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

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-[640px] flex-col bg-white">
      <header className="flex items-baseline justify-between bg-[var(--color-ink)] px-4 py-3 text-white">
        <span className="font-display text-lg font-bold tracking-tight">
          Wayfare
        </span>
        <span className="font-mono text-xs text-white/60">Itinerary</span>
      </header>

      <main className="flex flex-1 flex-col gap-4 p-4">
        {error && (
          <p role="alert" className="font-sans text-sm text-[var(--color-coral)]">
            {error}
          </p>
        )}

        {!loading && !error && rows.length === 0 && (
          <p className="font-sans text-sm text-[var(--color-slate)]">
            No bookings yet. Start a trip in chat to see it here.
          </p>
        )}

        {rows.map((row) => (
          <BookingCard
            key={row.id}
            booking={toBooking(row)}
            onApprove={() => act(row.id, "approve")}
            onReject={() => act(row.id, "reject")}
          />
        ))}
      </main>
    </div>
  );
}
