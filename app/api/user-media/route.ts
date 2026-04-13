import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import {
  INTERNAL_BACKEND_URL,
  internalBackendHeaders,
} from "@/lib/internal-backend";
import { NextRequest, NextResponse } from "next/server";

/** Avoid hung Media Library when the FastAPI / DB call never returns (wrong URL, pool exhaustion). */
const BACKEND_FETCH_MS = 30_000;

export async function GET(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const type = searchParams.get("type") || "";
  const qs = type ? `?type=${encodeURIComponent(type)}` : "";

  const url = `${INTERNAL_BACKEND_URL}/internal/user-media${qs}`;
  let res: Response;
  try {
    res = await fetch(url, {
      headers: internalBackendHeaders({ "x-user-email": session.user.email }),
      cache: "no-store",
      signal: AbortSignal.timeout(BACKEND_FETCH_MS),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut =
      e instanceof Error &&
      (e.name === "TimeoutError" || e.name === "AbortError");
    return NextResponse.json(
      {
        error: timedOut
          ? "Media service timed out. Check backend logs and DATABASE_URL / pool."
          : "Cannot reach media backend",
        detail: msg,
        items: [],
      },
      { status: timedOut ? 504 : 502 },
    );
  }

  const raw = await res.text();
  let data: Record<string, unknown>;
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON from media backend", items: [] },
      { status: 502 },
    );
  }

  if (!res.ok) {
    const detail =
      (typeof data.detail === "string" && data.detail) ||
      (typeof data.error === "string" && data.error) ||
      `Backend HTTP ${res.status}`;
    return NextResponse.json(
      { error: "Backend error", detail, items: [] },
      { status: res.status },
    );
  }

  return NextResponse.json(data);
}
