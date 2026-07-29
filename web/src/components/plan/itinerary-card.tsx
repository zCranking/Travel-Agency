import { Badge, RiskLabel } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

// Shapes as returned by POST /trips/{id}/plan (api/routes/planning.py).
export type PlannedLeg = {
  origin: string;
  destination: string;
  depart_at: string;
  arrive_at: string;
  airline: string;
  fare_class: string;
  price_cents: number;
  stops: number;
  offer_id: string | null;
};

export type Violation = {
  kind: string;
  severity: "hard" | "soft";
  message: string;
  meeting_id: string | null;
};

export type RiskAssessment = {
  severity: "low" | "medium" | "high";
  advisory: string;
  recommendations: string[];
  factors: { code: string; detail: string }[];
};

export type PlannedItinerary = {
  id: string;
  legs: PlannedLeg[];
  total_price_cents: number;
  soft_violations: Violation[];
  rank: number | null;
  rationale: string;
  concerns: string[];
  risk: RiskAssessment;
};

function money(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function clock(iso: string): string {
  return new Date(iso)
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    .replace(" AM", "a")
    .replace(" PM", "p");
}

function weekday(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { weekday: "short" });
}

// "Tue 6:00a — 10:00a", and "Tue 11:40p — Wed 7:05a" when it lands the next
// day. Saying which day matters more here than saving the four characters.
function legWindow(leg: PlannedLeg): string {
  const sameDay =
    new Date(leg.depart_at).toDateString() ===
    new Date(leg.arrive_at).toDateString();
  return `${weekday(leg.depart_at)} ${clock(leg.depart_at)} — ${
    sameDay ? "" : `${weekday(leg.arrive_at)} `
  }${clock(leg.arrive_at)}`;
}

function stops(count: number): string {
  return count === 0 ? "Nonstop" : `${count} stop${count > 1 ? "s" : ""}`;
}

export function ItineraryCard({
  itinerary,
  onSelect,
  busy,
}: {
  itinerary: PlannedItinerary;
  onSelect: (id: string) => void;
  busy?: boolean;
}) {
  const { risk } = itinerary;

  return (
    <article className="animate-(--animate-rise-in) rounded-2xl border border-(--color-line) bg-white p-5">
      <div className="flex items-baseline gap-3">
        {itinerary.rank !== null && (
          <Badge tone="pending">#{itinerary.rank}</Badge>
        )}
        <span className="font-mono text-[15px] font-semibold text-(--color-ink)">
          {money(itinerary.total_price_cents)}
        </span>
        <span className="ml-auto font-mono text-[11px] text-(--color-mute)">
          {itinerary.legs.length} leg{itinerary.legs.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* legs, as a timeline */}
      <ol className="mt-4 flex flex-col gap-3 border-l border-dashed border-[#d8d2c6] pl-4">
        {itinerary.legs.map((leg, i) => (
          <li key={`${leg.origin}-${leg.destination}-${i}`}>
            <div className="font-display text-[15px] font-semibold text-(--color-ink)">
              {leg.origin} → {leg.destination}
            </div>
            <div className="font-mono text-xs text-(--color-slate)">
              {legWindow(leg)}
            </div>
            <div className="font-sans text-xs text-(--color-mute)">
              {leg.airline} · {leg.fare_class} · {stops(leg.stops)}
            </div>
          </li>
        ))}
      </ol>

      {itinerary.rationale && (
        <p className="mt-4 font-sans text-sm text-(--color-ink)">
          {itinerary.rationale}
        </p>
      )}

      {/* A soft violation is shown, never hidden — that is the point of it
          being soft. Out of policy routes to the approval path that exists. */}
      {(itinerary.concerns.length > 0 ||
        itinerary.soft_violations.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {itinerary.soft_violations.map((violation, i) => (
            <Badge key={`v-${i}`} tone="outOfPolicy">
              {violation.message}
            </Badge>
          ))}
          {itinerary.concerns.map((concern, i) => (
            <Badge key={`c-${i}`} tone="outOfPolicy">
              {concern}
            </Badge>
          ))}
        </div>
      )}

      {/* risk — severity, advice, then the factors it was derived from, so a
          wrong severity is visibly wrong rather than a black box. */}
      <div className="mt-4 rounded-xl border border-(--color-line) bg-[#fbfaf8] p-4">
        <div className="flex items-baseline gap-3">
          <RiskLabel level={risk.severity}>
            {risk.severity.toUpperCase()} RISK
          </RiskLabel>
        </div>
        {risk.advisory && (
          <p className="mt-2 font-sans text-sm text-(--color-ink)">
            {risk.advisory}
          </p>
        )}
        {risk.recommendations.length > 0 && (
          <ul className="mt-2 list-disc pl-5 font-sans text-sm text-(--color-slate)">
            {risk.recommendations.map((recommendation, i) => (
              <li key={`r-${i}`}>{recommendation}</li>
            ))}
          </ul>
        )}
        {risk.factors.length > 0 && (
          <dl className="mt-3 flex flex-col gap-0.5 font-mono text-[11px] text-(--color-mute)">
            {risk.factors.map((factor) => (
              <div key={factor.code} className="flex gap-2">
                <dt className="uppercase">{factor.code}</dt>
                <dd>{factor.detail}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <div className="mt-4 flex items-center gap-3">
        <Button
          variant="confirm"
          disabled={busy}
          onClick={() => onSelect(itinerary.id)}
        >
          {busy ? "Checking the fare…" : "Select and book"}
        </Button>
        <span className="font-sans text-xs text-(--color-mute)">
          We reprice before booking — any increase asks first.
        </span>
      </div>
    </article>
  );
}
