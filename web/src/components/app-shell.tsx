"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { CalendarClock, Home, MessageCircle, ShieldCheck, Ticket } from "lucide-react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { cn } from "@/lib/utils";

// ponytail: only routes that exist. The design also shows Search/Team/Analytics —
// add each when it has a page behind it.
const NAV = [
  { href: "/home", label: "Home", icon: Home },
  { href: "/plan", label: "Plan", icon: CalendarClock },
  { href: "/itinerary", label: "Trips", icon: Ticket },
  { href: "/duty-of-care", label: "Duty of care", icon: ShieldCheck },
] as const;

function initials(name: string): string {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function navLinkClass(active: boolean): string {
  return cn(
    "flex items-center gap-2.5 rounded-[9px] px-3 py-2.5 font-sans text-sm font-medium transition-colors duration-[var(--duration-quick)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none",
    active
      ? "bg-[var(--color-ink)] text-white"
      : "text-[#5b6472] hover:bg-[rgba(27,42,65,0.05)] hover:text-[var(--color-ink)]",
  );
}

function Sidebar() {
  const pathname = usePathname();
  const [who, setWho] = useState<{ name: string; company: string } | null>(null);
  // Chat is per-trip, so the sidebar shortcut opens the most recently created
  // trip's thread (same "latest trip" convention /duty-of-care uses server-side).
  const [chatTripId, setChatTripId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const {
        data: { user },
      } = await supabaseBrowserClient.auth.getUser();
      if (!user) return;
      const { data } = await supabaseBrowserClient
        .from("employees")
        .select("id, name, companies(name)")
        .eq("auth_user_id", user.id)
        .maybeSingle();
      if (!active || !data) return;
      const company = data.companies as unknown as { name: string } | null;
      setWho({ name: data.name as string, company: company?.name ?? "" });

      const { data: trip } = await supabaseBrowserClient
        .from("trips")
        .select("id")
        .eq("employee_id", data.id as string)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (active && trip) setChatTripId(trip.id as string);
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <aside className="flex w-[236px] flex-none flex-col border-r border-[var(--color-line)] bg-white px-4 py-5">
      <Link
        href="/home"
        className="flex items-center gap-2.5 rounded-lg px-2 pb-5 focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none"
      >
        <span
          aria-hidden
          className="flex size-[22px] items-center justify-center rounded-md bg-[var(--color-ink)]"
        >
          <span className="size-2 rounded-[2px] bg-[var(--color-amber)]" />
        </span>
        <span className="font-display text-[19px] font-bold tracking-[-0.02em] text-[var(--color-ink)]">
          Wayfare
        </span>
      </Link>

      <nav className="flex flex-col gap-0.5">
        <Link
          href="/home"
          aria-current={
            pathname === "/home" || pathname.startsWith("/home/")
              ? "page"
              : undefined
          }
          className={navLinkClass(
            pathname === "/home" || pathname.startsWith("/home/"),
          )}
        >
          <Home aria-hidden className="size-[18px]" strokeWidth={1.7} />
          Home
        </Link>

        <Link
          href={chatTripId ? `/chat/${chatTripId}` : "#"}
          aria-current={pathname.startsWith("/chat/") ? "page" : undefined}
          aria-disabled={!chatTripId}
          onClick={(e) => {
            if (!chatTripId) e.preventDefault();
          }}
          className={cn(
            navLinkClass(pathname.startsWith("/chat/")),
            !chatTripId && "pointer-events-none opacity-50",
          )}
        >
          <MessageCircle aria-hidden className="size-[18px]" strokeWidth={1.7} />
          Chat
        </Link>

        {NAV.slice(1).map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={navLinkClass(active)}
            >
              <Icon aria-hidden className="size-[18px]" strokeWidth={1.7} />
              {label}
            </Link>
          );
        })}
      </nav>

      {who && (
        <Link
          href="/profile"
          aria-current={pathname === "/profile" ? "page" : undefined}
          className={cn(
            "mt-auto flex items-center gap-2.5 rounded-[9px] border-t border-[var(--color-line)] px-2 pt-4 pb-1 transition-colors duration-[var(--duration-quick)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none",
            pathname === "/profile"
              ? "bg-[rgba(27,42,65,0.05)]"
              : "hover:bg-[rgba(27,42,65,0.05)]",
          )}
        >
          <span
            aria-hidden
            className="flex size-8 flex-none items-center justify-center rounded-full bg-[var(--color-teal)] font-sans text-[13px] font-semibold text-white"
          >
            {initials(who.name)}
          </span>
          <span className="min-w-0 leading-tight">
            <span className="block truncate font-sans text-[13px] font-semibold text-[var(--color-ink)]">
              {who.name}
            </span>
            <span className="block truncate font-mono text-[11px] text-[var(--color-slate)]">
              {who.company}
            </span>
          </span>
        </Link>
      )}
    </aside>
  );
}

/**
 * Page chrome for every signed-in surface: fixed sidebar, scrolling main region.
 * `title`/`meta` render the white page header the design puts above each screen;
 * omit them for surfaces that supply their own full-bleed header (the dashboard).
 */
export function AppShell({
  title,
  meta,
  actions,
  children,
}: {
  title?: string;
  meta?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-dvh w-full bg-[var(--color-paper)]">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        {title && (
          <header className="flex flex-none items-center gap-4 border-b border-[var(--color-line)] bg-white px-7 py-4">
            <div>
              <h1 className="font-display text-[21px] font-semibold tracking-[-0.01em] text-[var(--color-ink)]">
                {title}
              </h1>
              {meta && (
                <p className="font-mono text-xs text-[var(--color-mute)]">
                  {meta}
                </p>
              )}
            </div>
            {actions && <div className="ml-auto flex items-center gap-3">{actions}</div>}
          </header>
        )}
        {children}
      </div>
    </div>
  );
}
