import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import {
  INTERNAL_BACKEND_URL,
  internalBackendHeaders,
} from "@/lib/internal-backend";
import { NextRequest, NextResponse } from "next/server";

/** FastAPI /internal/user-media — allow headroom for Postgres under load (jobs holding pool slots). */
const BACKEND_FETCH_MS = 120_000;

export const dynamic = "force-dynamic";

function mediaErrorJson(
  error: string,
  detail: string,
  status: number,
): NextResponse {
  return NextResponse.json({ error, detail, items: [] }, { status });
}

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
    return mediaErrorJson(
      timedOut
        ? "Media service timed out"
        : "Cannot reach media backend",
      timedOut
        ? "Increase DB pool or reduce long-running jobs; verify INTERNAL_BACKEND_URL."
        : msg,
      timedOut ? 504 : 502,
    );
  }

  const raw = await res.text();
  let data: Record<string, unknown>;
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    const hint = raw.trim().slice(0, 160);
    return mediaErrorJson(
      "Invalid JSON from media backend",
      hint
        ? `Non-JSON body (often proxy HTML): ${hint}`
        : "Empty body — check nginx/Cloudflare and INTERNAL_API_SECRET.",
      502,
    );
  }

  if (!res.ok) {
    const detail =
      (typeof data.detail === "string" && data.detail) ||
      (typeof data.error === "string" && data.error) ||
      `Backend HTTP ${res.status}`;
    return mediaErrorJson("Backend error", detail, res.status);
  }

  const items = Array.isArray(data.items) ? data.items : [];
  return NextResponse.json({ items });
}
