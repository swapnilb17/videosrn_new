import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import {
  INTERNAL_BACKEND_URL,
  internalBackendHeaders,
} from "@/lib/internal-backend";
import { NextRequest, NextResponse } from "next/server";

/**
 * Stream media downloads through Next.js (avoids S3 CORS in the browser).
 * Path is in the URL segments (not query) so nginx/proxies do not break on %2F in ?path=.
 */
export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path?: string[] }> },
) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path: segments } = await context.params;
  if (!segments?.length) {
    return NextResponse.json({ error: "Missing path" }, { status: 400 });
  }

  const pathname = `/${segments.join("/")}`;
  if (!pathname.startsWith("/media/") || pathname.includes("..")) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  const filenameParam = request.nextUrl.searchParams.get("filename");

  const backend = INTERNAL_BACKEND_URL.replace(/\/$/, "");
  const hasAttachment = /[?&]attachment=/.test(pathname);
  const upstreamUrl = hasAttachment
    ? `${backend}${pathname}`
    : `${backend}${pathname}${pathname.includes("?") ? "&" : "?"}attachment=1`;

  const cookie = request.headers.get("cookie") ?? "";
  const user = session.user as { email?: string | null; id?: string | null };
  const email = (user.email ?? "").trim();
  const sub = (user.id ?? "").trim();

  const headers: Record<string, string> = { cookie };
  // FastAPI /media OAuth checks session cookie; NextAuth cookie is different. When
  // INTERNAL_API_SECRET is set, trust X-User-Sub from our verified NextAuth session.
  if (sub) {
    Object.assign(
      headers,
      internalBackendHeaders({
        ...(email ? { "x-user-email": email } : {}),
        "x-user-sub": sub,
      }),
    );
  }

  const upstream = await fetch(upstreamUrl, {
    method: "GET",
    headers,
    redirect: "follow",
  });

  if (!upstream.ok) {
    const detail =
      upstream.status === 401
        ? "Sign in required to download this file."
        : "Could not fetch file from server.";
    return NextResponse.json({ error: detail }, { status: upstream.status });
  }

  const safeName = (filenameParam || "download")
    .replace(/[/\\?%*:|"<>]/g, "-")
    .slice(0, 180);

  const upstreamDisp = upstream.headers.get("content-disposition");
  const disposition =
    upstreamDisp && upstreamDisp.toLowerCase().includes("attachment")
      ? upstreamDisp
      : `attachment; filename="${safeName}"`;

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") || "application/octet-stream",
      "Content-Disposition": disposition,
      "Cache-Control": "private, no-store",
    },
  });
}
