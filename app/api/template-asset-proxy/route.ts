/**
 * Same-origin proxy for short-lived S3 presigned URLs of public template
 * assets. The browser cannot `fetch()` those URLs directly because the S3
 * bucket isn't configured with CORS for our origin — `<img>` and `<video>`
 * elements work fine (CORS isn't required for media tags) but reading the
 * bytes into a Blob/File for re-upload as a start frame / reference image
 * is blocked.
 *
 * This route is intentionally narrow:
 *   - GET only
 *   - Auth-gated (must be a signed-in dashboard user)
 *   - Strict hostname allowlist — currently `*.amazonaws.com` to match the
 *     S3 endpoints our backend signs against. Add more hosts if a CDN is
 *     introduced.
 *   - Streams the upstream body through unmodified, preserving content-type.
 */

import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

const ALLOWED_HOST_SUFFIXES = [".amazonaws.com"] as const;
const MAX_UPSTREAM_BYTES = 25 * 1024 * 1024; // 25 MB hard cap

function isAllowedAssetUrl(raw: string): URL | null {
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:") return null;
  const host = parsed.hostname.toLowerCase();
  const ok = ALLOWED_HOST_SUFFIXES.some((suffix) => host.endsWith(suffix));
  return ok ? parsed : null;
}

export async function GET(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const raw = request.nextUrl.searchParams.get("url");
  if (!raw) {
    return NextResponse.json({ error: "Missing url" }, { status: 400 });
  }

  const target = isAllowedAssetUrl(raw);
  if (!target) {
    return NextResponse.json(
      { error: "Asset host is not allowed" },
      { status: 403 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), {
      method: "GET",
      redirect: "follow",
      // Don't forward cookies — the URL is already presigned.
      headers: { Accept: "image/*,video/*;q=0.9,*/*;q=0.5" },
    });
  } catch {
    return NextResponse.json(
      { error: "Upstream fetch failed" },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    return NextResponse.json(
      { error: `Upstream returned ${upstream.status}` },
      { status: upstream.status },
    );
  }

  // Defend against absurdly large responses — start frames don't need 100 MB.
  const lenHeader = upstream.headers.get("content-length");
  if (lenHeader) {
    const len = Number(lenHeader);
    if (Number.isFinite(len) && len > MAX_UPSTREAM_BYTES) {
      return NextResponse.json(
        { error: "Asset too large" },
        { status: 413 },
      );
    }
  }

  const contentType =
    upstream.headers.get("content-type") || "application/octet-stream";

  return new NextResponse(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      // Short cache: presigned URLs rotate, but during a single edit session
      // the user may revisit the same template a few times.
      "Cache-Control": "private, max-age=120",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
