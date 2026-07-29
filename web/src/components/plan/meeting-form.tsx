"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * One meeting, as typed. Times are `datetime-local` values (a wall clock with
 * no zone) — the caller converts them with `new Date(v).toISOString()` before
 * they leave the browser, because the API rejects naive datetimes on purpose.
 */
export type MeetingDraft = {
  title: string;
  city: string;
  mode: "in_person" | "virtual";
  starts_at: string;
  ends_at: string;
  flexible: boolean;
};

const EMPTY: MeetingDraft = {
  title: "",
  city: "",
  mode: "in_person",
  starts_at: "",
  ends_at: "",
  flexible: false,
};

const LABEL =
  "font-mono text-[11px] uppercase tracking-wide text-(--color-slate)";
const INPUT =
  "rounded-lg border border-(--color-line) px-3 py-2 font-sans text-sm text-(--color-ink) focus-visible:border-(--color-teal) focus-visible:ring-2 focus-visible:ring-(--color-teal) focus-visible:outline-none disabled:bg-[#f4f2ee] disabled:text-(--color-mute)";

const MODES = [
  { value: "in_person", label: "In person" },
  { value: "virtual", label: "Virtual" },
] as const;

export function MeetingForm({
  onAdd,
}: {
  onAdd: (meeting: MeetingDraft) => void;
}) {
  const [draft, setDraft] = useState<MeetingDraft>(EMPTY);

  // An in-person meeting with no city is rejected by the API (and by the DB) —
  // a guessed city books a real ticket to the wrong place.
  const complete =
    draft.title.trim() !== "" &&
    draft.starts_at !== "" &&
    draft.ends_at !== "" &&
    (draft.mode === "virtual" || draft.city.trim() !== "");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!complete) return;
        onAdd({ ...draft, title: draft.title.trim(), city: draft.city.trim() });
        setDraft(EMPTY);
      }}
      className="rounded-xl border border-(--color-line) bg-white p-5"
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="meeting-title" className={LABEL}>
            What is it
          </label>
          <input
            id="meeting-title"
            value={draft.title}
            onChange={(e) =>
              setDraft((d) => ({ ...d, title: e.target.value }))
            }
            placeholder="Client pitch"
            className={INPUT}
          />
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1.5">
            <span className={LABEL}>Mode</span>
            <div className="flex gap-1 rounded-[9px] bg-[#f4f2ee] p-[3px]">
              {MODES.map(({ value, label }) => (
                <label
                  key={value}
                  className={cn(
                    "cursor-pointer rounded-[7px] px-3.5 py-1.5 font-sans text-[13px] transition-colors duration-(--duration-quick) has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-(--color-teal)",
                    draft.mode === value
                      ? "bg-white font-semibold text-(--color-ink) shadow-[0_1px_2px_rgba(27,42,65,0.08)]"
                      : "font-medium text-(--color-slate) hover:text-(--color-ink)",
                  )}
                >
                  <input
                    type="radio"
                    name="mode"
                    className="sr-only"
                    checked={draft.mode === value}
                    onChange={() =>
                      setDraft((d) => ({
                        ...d,
                        mode: value,
                        // A virtual meeting has no city to be present in.
                        city: value === "virtual" ? "" : d.city,
                      }))
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="meeting-city" className={LABEL}>
              City (IATA)
            </label>
            <input
              id="meeting-city"
              value={draft.city}
              disabled={draft.mode === "virtual"}
              maxLength={3}
              onChange={(e) =>
                setDraft((d) => ({ ...d, city: e.target.value.toUpperCase() }))
              }
              placeholder="ORD"
              className={cn(INPUT, "w-24 font-mono uppercase")}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="meeting-start" className={LABEL}>
              Starts
            </label>
            <input
              id="meeting-start"
              type="datetime-local"
              value={draft.starts_at}
              onChange={(e) =>
                setDraft((d) => ({ ...d, starts_at: e.target.value }))
              }
              className={INPUT}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="meeting-end" className={LABEL}>
              Ends
            </label>
            <input
              id="meeting-end"
              type="datetime-local"
              value={draft.ends_at}
              onChange={(e) =>
                setDraft((d) => ({ ...d, ends_at: e.target.value }))
              }
              className={INPUT}
            />
          </div>
        </div>

        <div className="flex items-center justify-between gap-4">
          <label className="flex items-center gap-2 font-sans text-sm text-(--color-slate)">
            <input
              type="checkbox"
              checked={draft.flexible}
              onChange={(e) =>
                setDraft((d) => ({ ...d, flexible: e.target.checked }))
              }
              className="size-4 accent-(--color-teal)"
            />
            This one can move
          </label>
          <Button type="submit" disabled={!complete}>
            Add meeting
          </Button>
        </div>
      </div>
    </form>
  );
}
