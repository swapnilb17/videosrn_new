"use client";

import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";
import { ApiError, checkCreditCode, redeemStarterCode } from "@/lib/api";

export default function SettingsPage() {
  const { credits, creditsInfo, creditsLoading, creditsError, refreshCredits } = useAuth();
  const [code, setCode] = useState("");
  const [redeemMsg, setRedeemMsg] = useState<string | null>(null);
  const [redeeming, setRedeeming] = useState(false);
  const [checking, setChecking] = useState(false);

  async function handleCheckCode() {
    setRedeemMsg(null);
    const trimmed = code.trim();
    if (!trimmed) {
      setRedeemMsg("Enter a code first.");
      return;
    }
    setChecking(true);
    try {
      const r = await checkCreditCode(trimmed);
      setRedeemMsg(
        r.message ||
          (r.valid ? "Code looks valid — you can redeem it." : "Code is not valid for redemption."),
      );
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Could not check code";
      setRedeemMsg(msg);
    } finally {
      setChecking(false);
    }
  }

  async function handleRedeem(e: React.FormEvent) {
    e.preventDefault();
    setRedeemMsg(null);
    setRedeeming(true);
    try {
      await redeemStarterCode(code.trim());
      setRedeemMsg(
        "Redeemed successfully — credits were added per the code. Starter (Veo and premium models) stays available while you have balance.",
      );
      setCode("");
      refreshCredits();
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError
          ? err.detail
          : err instanceof Error
            ? err.message
            : "Could not redeem code";
      setRedeemMsg(msg);
    } finally {
      setRedeeming(false);
    }
  }

  const planLabel =
    creditsInfo?.plan === "starter" ? "Starter" : "Free";

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <Card className="space-y-3 p-4">
        <p className="text-lg font-semibold">Credits &amp; plan</p>
        <p className="text-sm text-slate-300">
          1 credit equals ₹1. New accounts receive 50 credits once. Redeeming
          Starter tops you up to 500 credits if your balance is below that.
          Standard video (Topic → Video) bills about 0.75 credits per second of
          target duration (rounded up), or 1.75/sec when Enhance mode is on.
          Images cost 5 credits each; voice uses 2 credits per 2,000 characters.
          Veo (premium) requires Starter and bills 15–25 credits per second by
          tier.
        </p>
        {creditsError ? (
          <p className="text-sm text-red-300/90">
            Could not load credits: {creditsError}. Check that the backend is running
            and the frontend can reach it (e.g.{" "}
            <code className="rounded bg-white/10 px-1">INTERNAL_BACKEND_URL</code> in
            Docker).{" "}
            <button
              type="button"
              className="text-purple-300 underline hover:text-purple-200"
              onClick={() => refreshCredits()}
            >
              Retry
            </button>
          </p>
        ) : creditsLoading ? (
          <p className="text-sm text-slate-400">Loading credits…</p>
        ) : (
          <div className="flex flex-wrap gap-4 text-sm">
            <span>
              Balance:{" "}
              <span className="font-semibold text-orange-200">{credits}</span>{" "}
              credits
            </span>
            <span>
              Plan: <span className="font-semibold">{planLabel}</span>
            </span>
          </div>
        )}
        {!creditsError && !creditsLoading && creditsInfo?.creditsEnabled === false ? (
          <p className="text-sm text-amber-200/90">
            Credits are not active on this server (backend needs{" "}
            <code className="rounded bg-white/10 px-1">DATABASE_URL</code> and{" "}
            <code className="rounded bg-white/10 px-1">CREDITS_ENABLED</code>
            ). Balance will stay at 0 until that is fixed.
          </p>
        ) : null}
      </Card>

      <Card className="space-y-3 p-4">
        <p className="text-lg font-semibold">Invite &amp; credit codes</p>
        <p className="text-sm text-slate-300">
          Enter a code you received to unlock Starter (Veo and premium models) and add
          credits. Credit promos add a fixed bundle and can each be used only once
          worldwide. The Starter invite tops your balance up toward 500 credits if you
          are below that. Use <strong className="font-medium text-slate-200">Check code</strong>{" "}
          to confirm a code before redeeming.
        </p>
        {creditsInfo?.starterRedeemAvailable === false &&
        creditsInfo?.plan !== "starter" ? (
          <p className="text-sm text-slate-400">
            Starter invite is marked used on this account — you can still redeem a credit
            promo below if you have a separate code.
          </p>
        ) : creditsInfo?.plan === "starter" ? (
          <p className="text-sm text-emerald-300/90">
            Starter is active. You can still redeem a one-time credit promo code here if
            that code has not been used yet.
          </p>
        ) : null}
        <form onSubmit={handleRedeem} className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-end">
          <input
            className="min-w-[200px] flex-1 rounded-lg border border-white/15 bg-[#0d1020] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-purple-400/40"
            placeholder="Invite or promo code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            autoComplete="off"
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={checking || !code.trim()} onClick={handleCheckCode}>
              {checking ? "…" : "Check code"}
            </Button>
            <Button type="submit" disabled={redeeming || !code.trim()}>
              {redeeming ? "…" : "Redeem"}
            </Button>
          </div>
        </form>
        {redeemMsg && (
          <p className="text-sm text-slate-300 whitespace-pre-wrap">{redeemMsg}</p>
        )}
      </Card>

      <Card className="space-y-2 p-4">
        <p className="text-lg font-semibold">Workspace preferences</p>
        <p className="text-sm text-slate-300">
          Defaults for voice, aspect ratio, and style presets can be configured
          from each creation tool.
        </p>
      </Card>
    </div>
  );
}
