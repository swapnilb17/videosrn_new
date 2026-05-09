import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import {
  INTERNAL_BACKEND_URL,
  internalBackendHeaders,
} from "@/lib/internal-backend";
import { NextRequest, NextResponse } from "next/server";

/** Same headroom as /credits/me — usage hits Postgres for filter + aggregate. */
const BACKEND_FETCH_MS = 90_000;

const FORWARDED_PARAMS = [
  "range",
  "from",
  "to",
  "kind",
  "page",
  "page_size",
  "format",
] as const;

const usageJsonFallback = (
  error: string,
  detail: string,
  status: number,
) =>
  NextResponse.json(
    {
      error,
      detail,
      credits_enabled: false,
      balance: 0,
      plan: "free",
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
      summary: {
        period_start: null,
        period_end: null,
        total_charged: 0,
        total_granted: 0,
        total_refunded: 0,
        current_balance: 0,
        by_query_type: [],
      },
    },
    { status },
  );

export async function GET(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const sub = (session.user as { id?: string }).id;

  const url = new URL(request.url);
  const search = new URLSearchParams();
  for (const key of FORWARDED_PARAMS) {
    const v = url.searchParams.get(key);
    if (v !== null && v !== "") search.set(key, v);
  }
  const isCsv = (search.get("format") || "").toLowerCase() === "csv";

  let res: Response;
  try {
    res = await fetch(
      `${INTERNAL_BACKEND_URL}/internal/credits/me/usage${search.size ? `?${search.toString()}` : ""}`,
      {
        headers: internalBackendHeaders({
          "x-user-email": session.user.email,
          ...(sub ? { "x-user-sub": sub } : {}),
        }),
        cache: "no-store",
        signal: AbortSignal.timeout(BACKEND_FETCH_MS),
      },
    );
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut =
      e instanceof Error &&
      (e.name === "TimeoutError" || e.name === "AbortError");
    if (isCsv) {
      return new NextResponse(
        `Error: ${timedOut ? "Billing service timed out" : "Cannot reach billing backend"} — ${msg}`,
        { status: timedOut ? 504 : 502 },
      );
    }
    return usageJsonFallback(
      timedOut ? "Billing service timed out" : "Cannot reach billing backend",
      msg,
      timedOut ? 504 : 502,
    );
  }

  if (isCsv) {
    // Stream the CSV body straight through. On error, surface a plain-text
    // message so the browser's auto-download produces a readable file.
    const body = await res.text();
    if (!res.ok) {
      return new NextResponse(`Error: HTTP ${res.status} — ${body.slice(0, 200)}`, {
        status: res.status,
      });
    }
    const headers: Record<string, string> = {
      "content-type":
        res.headers.get("content-type") || "text/csv; charset=utf-8",
    };
    const dispo = res.headers.get("content-disposition");
    if (dispo) headers["content-disposition"] = dispo;
    return new NextResponse(body, { status: 200, headers });
  }

  const raw = await res.text();
  let data: Record<string, unknown>;
  try {
    data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
  } catch {
    return usageJsonFallback(
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
    return usageJsonFallback(detail, detail, res.status);
  }

  return NextResponse.json(data);
}
