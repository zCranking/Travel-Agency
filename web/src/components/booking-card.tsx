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
  booked: { label: "BKD", mark: "✓", bg: "bg-[var(--color-teal)] text-white" },
  pending_approval: {
    label: "PEND",
    mark: "…",
    bg: "bg-[var(--color-coral)] text-white",
  },
  rejected: {
    label: "REJ",
    mark: "✕",
    bg: "bg-[var(--color-slate)] text-white",
  },
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
 * Boarding-pass stub — the signature element the whole design hangs on. A main
 * stub with the trip detail, a perforation, and a rotated status stamp.
 */
export function BookingCard({ booking }: { booking: Booking }) {
  const status = booking.status ?? "booked";
  const { label, mark, bg } = STATUS[status];

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
    <div className="flex overflow-hidden rounded-xl bg-[var(--color-paper)] shadow-[0_1px_3px_rgba(27,42,65,0.08)]">
      <div className="flex-1 p-5">
        <div className="flex items-baseline justify-between gap-3">
          <span className="font-sans text-[17px] font-bold text-[var(--color-ink)]">
            {title}
          </span>
          <span className="font-mono text-xs uppercase text-[var(--color-slate)]">
            {subLabel}
          </span>
        </div>
        <div className="mt-1.5 font-mono text-[15px] text-[var(--color-ink)]">
          {route}
        </div>
        <div className="mt-1.5 flex items-baseline justify-between gap-3 font-mono text-sm text-[var(--color-ink)]">
          <span>{when}</span>
          <span className="font-semibold">{price}</span>
        </div>
        <div className="mt-3 border-t border-dashed border-[#cfc9bd] pt-2 font-mono text-xs text-[var(--color-slate)]">
          CONF&nbsp;&nbsp;
          {booking.confirmation_code ??
            (status === "pending_approval" ? "— · awaiting approval" : "—")}
        </div>
      </div>

      <div className="flex items-center border-l-2 border-dashed border-[#cfc9bd]">
        <div
          className={cn(
            "m-2 flex -rotate-2 flex-col items-center gap-0.5 rounded-[5px] px-2.5 py-3.5",
            bg,
          )}
        >
          <span aria-hidden className="text-sm leading-none">
            {mark}
          </span>
          <span className="font-mono text-[10px] font-semibold tracking-[0.06em]">
            {label}
          </span>
        </div>
      </div>
    </div>
  );
}
