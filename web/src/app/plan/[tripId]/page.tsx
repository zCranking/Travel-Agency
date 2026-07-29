"use client";

import { use, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MeetingForm, type MeetingDraft } from "@/components/plan/meeting-form";
import {
  ItineraryCard,
  type PlannedItinerary,
  type Violation,
} from "@/components/plan/itinerary-card";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

// Rows as stored by the API (api/routes/planning.py).
type MeetingRow = {
  id: string;
  title: string;
  city: string | null;
  mode: "in_person" | "virtual";
  starts_at: string;
  ends_at: string;
  flexible: boolean;
};

type InterpretResponse = {
  origin_city: string | null;
  meetings: Omit<MeetingRow, "id">[];
  unresolved: string[];
};

type PlanResponse = {
  itineraries: PlannedItinerary[];
  binding_constraint: Violation | null;
  relaxation: string | null;
};

type SelectResponse = {
  status: "booked" | "needs_attention" | "reprice_required";
  unavailable?: string[];
  itinerary?: { id: string; total_price_cents: number };
  total_price_cents?: number;
};

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // FastAPI puts a string in `detail` for our own errors and a list for
    // validation failures; only the string is worth showing a human.
    const detail = (await res.json().catch(() => null))?.detail;
    throw new Error(
      typeof detail === "string" ? detail : `Request failed (${res.status})`,
    );
  }
  return (await res.json()) as T;
}

// ponytail: drafts show times in the browser's zone, not the meeting city's.
// It round-trips exactly (same zone both ways); a per-city clock would need an
// airport->timezone table the frontend has no reason to carry.
function toInputValue(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  return new Date(at.getTime() - at.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

function toPayload(draft: MeetingDraft) {
  return {
    title: draft.title,
    city: draft.mode === "virtual" ? null : draft.city.toUpperCase(),
    mode: draft.mode,
    // The API rejects a naive datetime on purpose — a wall clock with no zone
    // is how you plan a trip that misses the meeting.
    starts_at: new Date(draft.starts_at).toISOString(),
    ends_at: new Date(draft.ends_at).toISOString(),
    flexible: draft.flexible,
  };
}

function when(startIso: string, endIso: string): string {
  const time = { hour: "numeric", minute: "2-digit" } as const;
  const start = new Date(startIso).toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    ...time,
  });
  return `${start} — ${new Date(endIso).toLocaleTimeString("en-US", time)}`;
}

function money(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

const HEADING =
  "font-display text-[17px] font-semibold tracking-[-0.01em] text-(--color-ink)";
const CARD = "rounded-xl border border-(--color-line) bg-white p-5";

function MeetingLine({
  title,
  city,
  mode,
  starts_at,
  ends_at,
  flexible,
  onRemove,
}: Omit<MeetingRow, "id"> & { onRemove: () => void }) {
  return (
    <li className="flex items-center gap-3 border-b border-(--color-line) px-1 py-2.5 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="font-sans text-sm font-semibold text-(--color-ink)">
          {title}
        </div>
        <div className="font-mono text-xs text-(--color-slate)">
          {mode === "virtual" ? "Virtual" : city} · {when(starts_at, ends_at)}
        </div>
      </div>
      {flexible && <Badge tone="rejected">CAN MOVE</Badge>}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${title}`}
        className="rounded-lg p-1.5 text-(--color-slate) transition-colors duration-(--duration-quick) hover:bg-[rgba(27,42,65,0.05)] hover:text-(--color-ink) focus-visible:ring-2 focus-visible:ring-(--color-teal) focus-visible:outline-none"
      >
        <X aria-hidden className="size-4" strokeWidth={1.7} />
      </button>
    </li>
  );
}

export default function PlannerPage({
  params,
}: {
  params: Promise<{ tripId: string }>;
}) {
  const { tripId } = use(params);
  const router = useRouter();

  const [saved, setSaved] = useState<MeetingRow[]>([]);
  const [drafts, setDrafts] = useState<MeetingDraft[]>([]);
  const [text, setText] = useState("");
  const [unresolved, setUnresolved] = useState<string[]>([]);
  const [interpreting, setInterpreting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [reprice, setReprice] = useState<{
    itineraryId: string;
    totalCents: number;
    unavailable: string[];
  } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/trips/${tripId}/meetings`);
        if (!res.ok) throw new Error(`Could not load meetings (${res.status})`);
        const rows = (await res.json()) as MeetingRow[];
        if (active) setSaved(rows);
      } catch (e) {
        if (active)
          setError(e instanceof Error ? e.message : "Something went wrong.");
      }
    })();
    return () => {
      active = false;
    };
  }, [tripId]);

  async function readForMe() {
    setInterpreting(true);
    setError(null);
    try {
      const draft = await post<InterpretResponse>(
        `/trips/${tripId}/interpret`,
        { text },
      );
      setUnresolved(draft.unresolved);
      setDrafts((prev) => [
        ...prev,
        ...draft.meetings.map((m) => ({
          title: m.title,
          city: m.city ?? "",
          mode: m.mode,
          starts_at: toInputValue(m.starts_at),
          ends_at: toInputValue(m.ends_at),
          flexible: m.flexible,
        })),
      ]);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setInterpreting(false);
    }
  }

  async function saveMeetings() {
    setSaving(true);
    setError(null);
    try {
      const rows = await post<MeetingRow[]>(`/trips/${tripId}/meetings`, {
        meetings: drafts.map(toPayload),
      });
      setSaved((prev) => [...prev, ...rows]);
      setDrafts([]);
      setUnresolved([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  }

  async function removeSaved(id: string) {
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/meetings/${id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Could not remove it (${res.status})`);
      setSaved((prev) => prev.filter((m) => m.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  const findItineraries = useCallback(async () => {
    setPlanning(true);
    setError(null);
    setNotice(null);
    setReprice(null);
    try {
      setPlan(await post<PlanResponse>(`/trips/${tripId}/plan`, {}));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setPlanning(false);
    }
  }, [tripId]);

  async function select(itineraryId: string, confirmReprice = false) {
    setSelectingId(itineraryId);
    setError(null);
    setNotice(null);
    try {
      const result = await post<SelectResponse>(
        `/itineraries/${itineraryId}/select`,
        { confirm_reprice: confirmReprice },
      );
      if (result.status === "reprice_required") {
        setReprice({
          itineraryId,
          totalCents: result.itinerary?.total_price_cents ?? 0,
          unavailable: result.unavailable ?? [],
        });
        return;
      }
      setReprice(null);
      if (result.status === "booked") {
        router.push("/itinerary");
        return;
      }
      setNotice(
        "Booked what it could — something needs manager approval. Open Trips to see where it stands.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSelectingId(null);
    }
  }

  return (
    <AppShell title="Plan a trip" meta={`TRIP ${tripId.slice(0, 8)}`}>
      <div className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
        <div className="mx-auto flex max-w-[860px] flex-col gap-7">
          {error && (
            <p
              role="alert"
              className="flex items-center gap-2.5 rounded-xl border border-[rgba(193,84,60,0.35)] border-l-[3px] border-l-(--color-coral) bg-white px-4 py-3 font-sans text-sm text-(--color-ink)"
            >
              <span aria-hidden className="font-semibold text-(--color-coral)">
                !
              </span>
              {error}
            </p>
          )}

          {notice && (
            <p className="rounded-xl border border-(--color-line) bg-white px-4 py-3 font-sans text-sm text-(--color-ink)">
              {notice}
            </p>
          )}

          {/* 1 — paste box. Produces a draft; nothing is saved from it. */}
          <section>
            <h2 className={HEADING}>Paste an invite</h2>
            <p className="mt-1 mb-3 font-sans text-sm text-(--color-slate)">
              Drafted from your text — check it before saving. Nothing here is
              saved until you press Save meetings.
            </p>
            <div className={CARD}>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                rows={4}
                placeholder="I need to be in Chicago on the 14th at 2pm for a client pitch…"
                aria-label="Trip description"
                className="w-full resize-y rounded-lg border border-(--color-line) px-3 py-2 font-sans text-sm text-(--color-ink) placeholder:text-(--color-mute) focus-visible:border-(--color-teal) focus-visible:ring-2 focus-visible:ring-(--color-teal) focus-visible:outline-none"
              />
              <div className="mt-3">
                <Button
                  variant="secondary"
                  disabled={interpreting || text.trim() === ""}
                  onClick={readForMe}
                >
                  {interpreting ? "Reading…" : "Read this for me"}
                </Button>
              </div>
            </div>
          </section>

          {/* 2 — meetings. Drafts first, then what's actually saved. */}
          <section>
            <h2 className={HEADING}>Meetings you have to make</h2>
            <p className="mt-1 mb-3 font-sans text-sm text-(--color-slate)">
              A meeting is binding unless you say it can move. Binding is what
              the planner refuses to break.
            </p>

            {unresolved.length > 0 && (
              <div className="mb-3 rounded-xl border border-[rgba(232,163,61,0.45)] border-l-[3px] border-l-(--color-amber) bg-white px-4 py-3">
                <p className="font-sans text-sm font-semibold text-(--color-amber-ink)">
                  Couldn&apos;t work these out — add them yourself.
                </p>
                <ul className="mt-1 list-disc pl-5 font-sans text-sm text-(--color-slate)">
                  {unresolved.map((item, i) => (
                    <li key={`u-${i}`}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {(drafts.length > 0 || saved.length > 0) && (
              <div className={`${CARD} mb-3`}>
                {drafts.length > 0 && (
                  <>
                    <p className="mb-1 font-mono text-[11px] uppercase tracking-wide text-(--color-slate)">
                      Not saved yet
                    </p>
                    <ul className="mb-4">
                      {drafts.map((draft, i) => (
                        <MeetingLine
                          key={`d-${i}`}
                          title={draft.title}
                          city={draft.city}
                          mode={draft.mode}
                          starts_at={draft.starts_at}
                          ends_at={draft.ends_at}
                          flexible={draft.flexible}
                          onRemove={() =>
                            setDrafts((prev) =>
                              prev.filter((_, index) => index !== i),
                            )
                          }
                        />
                      ))}
                    </ul>
                    <Button
                      variant="confirm"
                      disabled={saving}
                      onClick={saveMeetings}
                    >
                      {saving ? "Saving…" : "Save meetings"}
                    </Button>
                  </>
                )}

                {saved.length > 0 && (
                  <>
                    <p
                      className={`mb-1 font-mono text-[11px] uppercase tracking-wide text-(--color-slate) ${drafts.length > 0 ? "mt-5" : ""}`}
                    >
                      Saved
                    </p>
                    <ul>
                      {saved.map((meeting) => (
                        <MeetingLine
                          key={meeting.id}
                          {...meeting}
                          onRemove={() => removeSaved(meeting.id)}
                        />
                      ))}
                    </ul>
                  </>
                )}
              </div>
            )}

            <MeetingForm
              onAdd={(meeting) => setDrafts((prev) => [...prev, meeting])}
            />
          </section>

          {/* 3 — solve. */}
          <section>
            <div className="flex items-center gap-3">
              <Button
                disabled={planning || saved.length === 0}
                onClick={findItineraries}
              >
                {planning ? "Working…" : "Find itineraries"}
              </Button>
              <span className="font-sans text-sm text-(--color-slate)">
                {planning
                  ? "Working through your constraints…"
                  : saved.length === 0
                    ? "Save at least one meeting first."
                    : "We search each hop, so this takes a few seconds."}
              </span>
            </div>
          </section>

          {/* 4 — results, or why there are none. */}
          {plan && (
            <section className="flex flex-col gap-4">
              {plan.binding_constraint ? (
                <div className="rounded-xl border border-[rgba(193,84,60,0.35)] border-l-[3px] border-l-(--color-coral) bg-white p-5">
                  <h2 className="font-display text-[17px] font-semibold text-(--color-ink)">
                    {plan.binding_constraint.message}
                  </h2>
                  {plan.relaxation && (
                    <p className="mt-2 font-sans text-sm text-(--color-slate)">
                      {plan.relaxation}
                    </p>
                  )}
                </div>
              ) : plan.itineraries.length === 0 ? (
                <p className="font-sans text-sm text-(--color-slate)">
                  No flights needed — every meeting on this trip is one you can
                  take from where you are.
                </p>
              ) : (
                <>
                  <h2 className={HEADING}>
                    {plan.itineraries.length === 1
                      ? "One itinerary makes every meeting"
                      : `${plan.itineraries.length} itineraries make every meeting`}
                  </h2>

                  {reprice && (
                    <div className="rounded-xl border border-[rgba(193,84,60,0.35)] border-l-[3px] border-l-(--color-coral) bg-white p-5">
                      {reprice.unavailable.length > 0 ? (
                        <>
                          <p className="font-sans text-sm text-(--color-ink)">
                            {reprice.unavailable.join(", ")} is no longer
                            available. Nothing was booked.
                          </p>
                          <div className="mt-3">
                            <Button variant="secondary" onClick={findItineraries}>
                              Plan again
                            </Button>
                          </div>
                        </>
                      ) : (
                        <>
                          <p className="font-sans text-sm text-(--color-ink)">
                            The fare moved to {money(reprice.totalCents)} since
                            we planned this.
                          </p>
                          <div className="mt-3 flex gap-3">
                            <Button
                              variant="confirm"
                              disabled={selectingId !== null}
                              onClick={() => select(reprice.itineraryId, true)}
                            >
                              Book at the new price
                            </Button>
                            <Button
                              variant="secondary"
                              onClick={() => setReprice(null)}
                            >
                              Keep looking
                            </Button>
                          </div>
                        </>
                      )}
                    </div>
                  )}

                  {plan.itineraries.map((itinerary) => (
                    <ItineraryCard
                      key={itinerary.id}
                      itinerary={itinerary}
                      busy={selectingId === itinerary.id}
                      onSelect={select}
                    />
                  ))}
                </>
              )}
            </section>
          )}
        </div>
      </div>
    </AppShell>
  );
}
