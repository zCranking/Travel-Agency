import { cn } from "@/lib/utils";

export type BookingStatus = "booked" | "pending_approval" | "rejected";

export type FlightBooking = {
  kind: "flight";
  id: string;
  airline: string;
  fare_class: string;
  origin: string;
  destination: string;
  depart_date: string;
  price_cents: number;
};

export type HotelBooking = {
  kind: "hotel";
  id: string;
  name: string;
  location: string;
  check_in: string;
  check_out: string;
  nightly_rate_cents: number;
};

export type Booking = (FlightBooking | HotelBooking) & {
  status?: BookingStatus;
  confirmation_code?: string;
};

const STATUS = {
  booked: { label: "BKD", bg: "bg-[var(--color-teal)]" },
  pending_approval: { label: "PEND", bg: "bg-[var(--color-coral)]" },
  rejected: { label: "REJ", bg: "bg-[var(--color-slate)]" },
} as const;

function money(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

// ponytail: only what today's data needs — no lib. add locale formatting when
// a non-US office actually asks.
function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Boarding-pass-stub card. Signature element shared by the chat inline results
 * and the Task 11 itinerary page: a torn ticket with a main stub and a rotated
 * status stub.
 */
export function BookingCard({ booking }: { booking: Booking }) {
  const status = booking.status ?? "booked";
  const { label, bg } = STATUS[status];

  const title = booking.kind === "flight" ? booking.airline : booking.name;
  const subLabel =
    booking.kind === "flight" ? booking.fare_class : booking.location;
  const route =
    booking.kind === "flight"
      ? `${booking.origin} → ${booking.destination}`
      : `${booking.check_in} – ${booking.check_out}`;
  const when =
    booking.kind === "flight"
      ? formatDate(booking.depart_date)
      : formatDate(booking.check_in);
  const price =
    booking.kind === "flight"
      ? money(booking.price_cents)
      : `${money(booking.nightly_rate_cents)}/night`;

  return (
    <div className="flex overflow-hidden rounded-lg bg-[var(--color-paper)] shadow-[0_1px_3px_rgba(27,42,65,0.08)]">
      {/* main stub */}
      <div className="flex-1 p-4">
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-sans text-base font-bold text-[var(--color-ink)]">
            {title}
          </span>
          <span className="font-mono text-xs uppercase tracking-wide text-[var(--color-slate)]">
            {subLabel}
          </span>
        </div>
        <div className="mt-1 font-mono text-sm text-[var(--color-ink)]">
          {route}
        </div>
        <div className="mt-1 flex items-baseline justify-between gap-3 font-mono text-sm text-[var(--color-ink)]">
          <span>{when}</span>
          <span className="font-medium">{price}</span>
        </div>
        <div className="mt-3 border-t border-dashed border-[var(--color-slate)] pt-2 font-mono text-xs text-[var(--color-slate)]">
          CONF&nbsp;&nbsp;{booking.confirmation_code ?? "—"}
        </div>
      </div>

      {/* perforation + status stub */}
      <div className="flex items-center border-l-2 border-dashed border-[var(--color-slate)]">
        <div
          className={cn(
            "m-2 flex flex-col items-center gap-0.5 rounded px-2 py-3 text-white",
            bg,
          )}
          style={{ transform: "rotate(-2deg)" }}
        >
          <span aria-hidden className="text-sm leading-none">
            {status === "booked" ? "✓" : status === "rejected" ? "✕" : "…"}
          </span>
          <span className="font-mono text-[10px] font-semibold tracking-wider">
            {label}
          </span>
        </div>
      </div>
    </div>
  );
}
