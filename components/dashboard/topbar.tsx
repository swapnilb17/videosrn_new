"use client";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { Coins } from "lucide-react";

export function DashboardTopbar() {
  const { credits, creditsLoading, creditsError, userName, logout } = useAuth();

  const creditsLine = creditsError
    ? "Credits unavailable"
    : creditsLoading
      ? "…"
      : `${credits} credits remaining`;

  return (
    <header className="flex items-center justify-between border-b border-white/10 bg-[#101427] px-6 py-4">
      <div className="flex items-center gap-2 text-sm text-slate-300">
        <Coins className="h-4 w-4 text-orange-300" />
        <span title={creditsError ?? undefined}>{creditsLine}</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-white/10 px-3 py-1 text-sm">{userName}</div>
        <Button variant="outline" size="sm" onClick={logout}>
          Logout
        </Button>
      </div>
    </header>
  );
}
