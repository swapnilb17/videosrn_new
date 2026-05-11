"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { Coins, LogOut, Menu, User } from "lucide-react";
import { Sheet } from "@/components/ui/sheet";
import { SidebarContent } from "@/components/dashboard/sidebar";
import { useAuth } from "@/lib/auth-context";

function initialsFrom(name: string | null | undefined): string {
  if (!name) return "U";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "U";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Compact topbar shown only on `< md`. Renders a hamburger that opens the
 * full sidebar in a left drawer, a short credits pill, and an avatar menu
 * with the user's name + logout. Desktop continues to use `DashboardTopbar`.
 */
export function MobileTopbar() {
  const { credits, creditsLoading, creditsError, userName, logout } = useAuth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  const creditsLabel = creditsError
    ? "—"
    : creditsLoading
      ? "…"
      : `${credits} cr`;

  return (
    <header className="flex items-center justify-between gap-2 border-b border-white/10 bg-[#101427] px-3 py-2 md:hidden">
      <button
        type="button"
        aria-label="Open navigation"
        onClick={() => setDrawerOpen(true)}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-200 transition active:bg-white/10"
      >
        <Menu className="h-5 w-5" />
      </button>

      <Link
        href="/dashboard"
        className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200"
        title={creditsError ?? undefined}
      >
        <Coins className="h-3.5 w-3.5 text-orange-300" />
        <span className="font-medium">{creditsLabel}</span>
      </Link>

      <button
        type="button"
        aria-label="Open account menu"
        onClick={() => setUserOpen(true)}
        className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-blue-500 text-xs font-semibold text-white shadow-[0_6px_18px_rgba(112,92,255,0.45)]"
      >
        {initialsFrom(userName)}
      </button>

      <Sheet
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        side="left"
        showHandle={false}
        showClose
        ariaLabel="Main navigation"
      >
        <Suspense fallback={null}>
          <SidebarContent onNavigate={() => setDrawerOpen(false)} />
        </Suspense>
      </Sheet>

      <Sheet
        open={userOpen}
        onClose={() => setUserOpen(false)}
        side="bottom"
        title="Account"
        description={userName ?? undefined}
      >
        <div className="space-y-2 pt-1">
          <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 p-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-purple-500 to-blue-500 text-sm font-semibold text-white">
              {initialsFrom(userName)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">
                {userName ?? "Signed in"}
              </p>
              <p className="text-xs text-slate-400">{creditsLabel} remaining</p>
            </div>
          </div>

          <Link
            href="/dashboard/settings"
            onClick={() => setUserOpen(false)}
            className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-200 transition active:bg-white/10"
          >
            <User className="h-4 w-4 text-slate-300" />
            Settings &amp; billing
          </Link>

          <button
            type="button"
            onClick={() => {
              setUserOpen(false);
              logout();
            }}
            className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-rose-200 transition active:bg-white/10"
          >
            <LogOut className="h-4 w-4" />
            Log out
          </button>
        </div>
      </Sheet>
    </header>
  );
}
