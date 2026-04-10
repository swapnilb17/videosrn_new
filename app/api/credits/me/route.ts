import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.INTERNAL_BACKEND_URL || "http://backend:8000";

export async function GET(_request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const sub = (session.user as { id?: string }).id;

  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/internal/credits/me`, {
      headers: {
        "x-user-email": session.user.email,
        ...(sub ? { "x-user-sub": sub } : {}),
      },
      cache: "no-store",
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      {
        error: "Cannot reach billing backend",
        detail: msg,
        credits_enabled: false,
        balance: 0,
        plan: "free",
      },
      { status: 502 },
    );
  }

  const raw = await res.text();
  let data: Record<string, unknown>;
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    return NextResponse.json(
      { error: "Invalid backend response", credits_enabled: false, balance: 0, plan: "free" },
      { status: 502 },
    );
  }

  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : `HTTP ${res.status}`;
    return NextResponse.json(
      {
        error: detail,
        credits_enabled: false,
        balance: 0,
        plan: "free",
      },
      { status: res.status },
    );
  }

  return NextResponse.json(data);
}
