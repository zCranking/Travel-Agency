"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Home, ShieldCheck, Ticket } from "lucide-react";
import { supabaseBrowserClient } from "@/lib/supabase";
import { cn } from "@/lib/utils";

// ponytail: only routes that exist. The design also shows Search/Team/Analytics —
// add each when it has a page behind it.
const NAV = [
  { href: "/home", label: "Home", icon: Home },
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

function Sidebar() {
  const pathname = usePathname();
  const [who, setWho] = useState<{ name: string; company: string } | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      const {
        data: { user },
      } = await supabaseBrowserClient.auth.getUser();
      if (!user) return;
      const { data } = await supabaseBrowserClient
        .from("employees")
        .select("name, companies(name)")
        .eq("auth_user_id", user.id)
        .maybeSingle();
      if (!active || !data) return;
      const company = data.companies as unknown as { name: string } | null;
      setWho({ name: data.name as string, company: company?.name ?? "" });
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
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-[9px] px-3 py-2.5 font-sans text-sm font-medium transition-colors duration-[var(--duration-quick)] focus-visible:ring-2 focus-visible:ring-[var(--color-teal)] focus-visible:outline-none",
                active
                  ? "bg-[var(--color-ink)] text-white"
                  : "text-[#5b6472] hover:bg-[rgba(27,42,65,0.05)] hover:text-[var(--color-ink)]",
              )}
            >
              <Icon aria-hidden className="size-[18px]" strokeWidth={1.7} />
              {label}
            </Link>
          );
        })}
      </nav>

      {who && (
        <div className="mt-auto flex items-center gap-2.5 border-t border-[var(--color-line)] px-2 pt-4">
          <span
            aria-hidden
            className="flex size-8 items-center justify-center rounded-full bg-[var(--color-teal)] font-sans text-[13px] font-semibold text-white"
          >
            {initials(who.name)}
          </span>
          <span className="leading-tight">
            <span className="block font-sans text-[13px] font-semibold text-[var(--color-ink)]">
              {who.name}
            </span>
            <span className="block font-mono text-[11px] text-[var(--color-slate)]">
              {who.company}
            </span>
          </span>
        </div>
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
