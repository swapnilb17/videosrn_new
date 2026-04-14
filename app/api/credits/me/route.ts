import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import {
  INTERNAL_BACKEND_URL,
  internalBackendHeaders,
} from "@/lib/internal-backend";
import { NextRequest, NextResponse } from "next/server";

/** Same headroom as user-media — credits hits Postgres under load (get_or_create_user). */
const BACKEND_FETCH_MS = 90_000;

const creditsFallback = (error: string, detail: string, status: number) =>
  NextResponse.json(
    {
      error,
      detail,
      credits_enabled: false,
      balance: 0,
      plan: "free",
      starter_redeem_available: false,
    },
    { status },
  );

export async function GET(_request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const sub = (session.user as { id?: string }).id;

  let res: Response;
  try {
    res = await fetch(`${INTERNAL_BACKEND_URL}/internal/credits/me`, {
      headers: internalBackendHeaders({
        "x-user-email": session.user.email,
        ...(sub ? { "x-user-sub": sub } : {}),
      }),
      cache: "no-store",
      signal: AbortSignal.timeout(BACKEND_FETCH_MS),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut =
      e instanceof Error &&
      (e.name === "TimeoutError" || e.name === "AbortError");
    return creditsFallback(
      timedOut ? "Billing service timed out" : "Cannot reach billing backend",
      msg,
      timedOut ? 504 : 502,
    );
  }

  const raw = await res.text();
  let data: Record<string, unknown>;
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    return creditsFallback(
      "Invalid backend response",
      "Backend returned non-JSON (often a proxy timeout HTML page).",
      502,
    );
  }

  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : `HTTP ${res.status}`;
    return creditsFallback(detail, detail, res.status);
  }

  const body = {
    credits_enabled: data.credits_enabled !== false,
    balance:
      typeof data.balance === "number"
        ? data.balance
        : Number(data.balance) || 0,
    plan: typeof data.plan === "string" ? data.plan : "free",
    starter_redeem_available: data.starter_redeem_available !== false,
  };
  return NextResponse.json(body);
}
