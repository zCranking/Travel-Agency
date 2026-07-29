"use client";

import { useEffect, useRef } from "react";

export type Message = { role: "user" | "assistant"; content: string };

/**
 * Renders the conversation thread. Assistant turns get a subtle paper-card
 * background (left-aligned); user turns are plain right-aligned ink text — no
 * two-tone bubbles, per the design direction.
 */
export function MessageList({
  messages,
  pending,
}: {
  messages: Message[];
  pending?: boolean;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, pending]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-6">
      {messages.length === 0 && (
        <div className="m-auto max-w-[420px] text-center">
          <p className="font-display text-lg font-semibold text-[var(--color-ink)]">
            Where do you need to be?
          </p>
          <p className="mt-1.5 font-sans text-sm text-[var(--color-slate)]">
            Say it in plain English — &ldquo;a flight from SFO to JFK on Sep
            1&rdquo; — and Wayfare searches, checks policy, and books it.
          </p>
        </div>
      )}
      {messages.map((m, i) =>
        m.role === "assistant" ? (
          <div
            key={i}
            className="animate-[var(--animate-message-in)] max-w-[85%] self-start rounded-lg bg-[var(--color-paper)] px-4 py-3 shadow-[0_1px_3px_rgba(27,42,65,0.08)]"
          >
            <p className="font-sans text-[15px] leading-relaxed whitespace-pre-wrap text-[var(--color-ink)]">
              {m.content}
            </p>
          </div>
        ) : (
          <div
            key={i}
            className="animate-[var(--animate-message-in)] max-w-[85%] self-end"
          >
            <p className="font-sans text-[15px] leading-relaxed whitespace-pre-wrap text-right text-[var(--color-ink)]">
              {m.content}
            </p>
          </div>
        ),
      )}
      {pending && (
        <div
          aria-label="Wayfare is replying"
          className="max-w-[85%] animate-[var(--animate-message-in)] self-start rounded-lg bg-[var(--color-paper)] px-4 py-3 shadow-[0_1px_3px_rgba(27,42,65,0.08)]"
        >
          <div className="flex flex-col gap-2">
            <div className="h-3 w-48 animate-pulse rounded bg-[rgba(27,42,65,0.12)]" />
            <div className="h-3 w-28 animate-pulse rounded bg-[rgba(27,42,65,0.12)]" />
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
