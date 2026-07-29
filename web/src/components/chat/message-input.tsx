"use client";

import { useState } from "react";
import { SendHorizontal } from "lucide-react";

/**
 * Bottom-pinned input bar. Amber send button, amber focus ring per the design
 * direction. Submits on Enter (Shift+Enter for newline) or the send button.
 */
export function MessageInput({
  onSend,
  disabled,
}: {
  onSend: (content: string) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");

  function submit() {
    const content = value.trim();
    if (!content || disabled) return;
    onSend(content);
    setValue("");
  }

  return (
    <form
      className="flex flex-none items-end gap-2 border-t border-[var(--color-line)] bg-white px-6 py-3.5"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        rows={1}
        placeholder="Where to?"
        aria-label="Message"
        className="max-h-32 flex-1 resize-none rounded-lg border border-[var(--color-slate)]/30 bg-[var(--color-paper)] px-3 py-2 font-sans text-[15px] text-[var(--color-ink)] placeholder:text-[var(--color-slate)] focus-visible:border-[var(--color-amber)] focus-visible:ring-2 focus-visible:ring-[var(--color-amber)] focus-visible:outline-none"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label="Send message"
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--color-amber)] text-[var(--color-ink)] transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--color-amber)] focus-visible:ring-offset-2 focus-visible:outline-none disabled:opacity-40"
      >
        <SendHorizontal className="h-5 w-5" />
      </button>
    </form>
  );
}
