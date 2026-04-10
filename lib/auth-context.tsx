"use client";

import { useSession, signOut } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";

export type CreditsInfo = {
  balance: number;
  plan: "free" | "starter";
  creditsEnabled: boolean;
  starterRedeemAvailable: boolean;
};

export function useAuth() {
  const { data: session, status } = useSession();
  const [creditsInfo, setCreditsInfo] = useState<CreditsInfo | null>(null);

  const loadCredits = useCallback(() => {
    if (status !== "authenticated" || !session?.user?.email) {
      setCreditsInfo(null);
      return;
    }
    fetch("/api/credits/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        setCreditsInfo({
          balance: typeof data.balance === "number" ? data.balance : 0,
          plan: data.plan === "starter" ? "starter" : "free",
          creditsEnabled: data.credits_enabled !== false,
          starterRedeemAvailable: data.starter_redeem_available !== false,
        });
      })
      .catch(() => {});
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
    refreshCredits: loadCredits,
    logout: () => signOut({ callbackUrl: "/" }),
  };
}
