"use client";

import { useSession, signOut } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";

export type CreditsInfo = {
  balance: number;
  plan: "free" | "starter";
  creditsEnabled: boolean;
  starterRedeemAvailable: boolean;
};

function parseBalance(raw: unknown): number {
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string") {
    const n = Number(raw);
    if (Number.isFinite(n)) return n;
  }
  return 0;
}

export function useAuth() {
  const { data: session, status } = useSession();
  const [creditsInfo, setCreditsInfo] = useState<CreditsInfo | null>(null);
  const [creditsLoading, setCreditsLoading] = useState(false);
  const [creditsError, setCreditsError] = useState<string | null>(null);

  const loadCredits = useCallback(() => {
    if (status !== "authenticated" || !session?.user?.email) {
      setCreditsInfo(null);
      setCreditsLoading(false);
      setCreditsError(null);
      return;
    }
    setCreditsLoading(true);
    setCreditsError(null);
    fetch("/api/credits/me", { credentials: "include" })
      .then(async (r) => {
        const text = await r.text();
        let data: Record<string, unknown> = {};
        try {
          data = text ? (JSON.parse(text) as Record<string, unknown>) : {};
        } catch {
          setCreditsInfo(null);
          setCreditsError("Invalid response from credits API");
          setCreditsLoading(false);
          return;
        }
        if (!r.ok) {
          const msg =
            (typeof data.error === "string" && data.error) ||
            (typeof data.detail === "string" && data.detail) ||
            `Credits API failed (${r.status})`;
          setCreditsInfo(null);
          setCreditsError(msg);
          setCreditsLoading(false);
          return;
        }
        setCreditsInfo({
          balance: parseBalance(data.balance),
          plan: data.plan === "starter" ? "starter" : "free",
          creditsEnabled: data.credits_enabled !== false,
          starterRedeemAvailable: data.starter_redeem_available !== false,
        });
        setCreditsLoading(false);
      })
      .catch((e: unknown) => {
        setCreditsInfo(null);
        setCreditsError(e instanceof Error ? e.message : "Network error loading credits");
        setCreditsLoading(false);
      });
  }, [status, session?.user?.email]);

  useEffect(() => {
    loadCredits();
  }, [loadCredits]);

  const userId =
    (session?.user as { id?: string } | undefined)?.id ?? "";

  return {
    isAuthenticated: status === "authenticated",
    isLoading: status === "loading",
    userName: session?.user?.name ?? "User",
    userEmail: session?.user?.email ?? "",
    userId,
    userImage: session?.user?.image ?? "",
    credits: creditsInfo?.balance ?? 0,
    creditsInfo,
    creditsLoading,
    creditsError,
    refreshCredits: loadCredits,
    logout: () => signOut({ callbackUrl: "/" }),
  };
}
