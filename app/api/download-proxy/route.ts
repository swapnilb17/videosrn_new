import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { INTERNAL_BACKEND_URL } from "@/lib/internal-backend";
import { NextRequest, NextResponse } from "next/server";

/**
 * Stream media downloads through Next.js so the browser does not need CORS on S3
 * after a 302 from /media (fetch(blob) would fail client-side).
 */
export async function GET(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const pathParam = request.nextUrl.searchParams.get("path");
  const filenameParam = request.nextUrl.searchParams.get("filename");

  if (!pathParam) {
    return NextResponse.json({ error: "Missing path" }, { status: 400 });
  }

  let pathname: string;
  try {
    const u = new URL(pathParam, "http://localhost");
    pathname = u.pathname + u.search;
  } catch {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  if (!pathname.startsWith("/media/") || pathname.includes("..")) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  const backend = INTERNAL_BACKEND_URL.replace(/\/$/, "");
  const hasAttachment = /[?&]attachment=/.test(pathname);
  const upstreamUrl = hasAttachment
    ? `${backend}${pathname}`
    : `${backend}${pathname}${pathname.includes("?") ? "&" : "?"}attachment=1`;

  const cookie = request.headers.get("cookie") ?? "";

  const upstream = await fetch(upstreamUrl, {
    method: "GET",
    headers: { cookie },
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
