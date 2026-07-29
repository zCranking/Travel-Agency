"use client";

import { use, useCallback, useEffect, useState } from "react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { MessageList, type Message } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import { AppShell } from "@/components/app-shell";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

export default function ChatPage({
  params,
}: {
  params: Promise<{ tripId: string }>;
}) {
  const { tripId } = use(params);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const { data, error } = await supabaseBrowserClient
        .from("trip_messages")
        .select("role, content, created_at")
        .eq("trip_id", tripId)
        .order("created_at", { ascending: true });
      if (!active) return;
      if (error) {
        setError(error.message);
        return;
      }
      setMessages(
        (data ?? []).map((m) => ({
          role: m.role as Message["role"],
          content: m.content as string,
        })),
      );
    })();
    return () => {
      active = false;
    };
  }, [tripId]);

  const handleSend = useCallback(
    async (content: string) => {
      setError(null);
      setSending(true);
      setMessages((prev) => [...prev, { role: "user", content }]);
      try {
        const res = await fetch(`${API_BASE}/trips/${tripId}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const { reply } = (await res.json()) as { reply: string };
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
      } finally {
        setSending(false);
      }
    },
    [tripId],
  );

  return (
    <AppShell title="Plan a trip" meta={`TRIP ${tripId.slice(0, 8)}`}>
      <div className="mx-auto flex min-h-0 w-full max-w-[760px] flex-1 flex-col">
        <MessageList messages={messages} pending={sending} />

        {error && (
          <p
            role="alert"
            className="mx-6 mb-2 flex items-center gap-2.5 rounded-xl border border-[rgba(193,84,60,0.35)] border-l-[3px] border-l-[var(--color-coral)] bg-white px-4 py-3 font-sans text-sm text-[var(--color-ink)]"
          >
            <span aria-hidden className="font-semibold text-[var(--color-coral)]">
              !
            </span>
            {error}
          </p>
        )}

        <MessageInput onSend={handleSend} disabled={sending} />
      </div>
    </AppShell>
  );
}
