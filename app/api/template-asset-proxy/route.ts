/**
 * Same-origin proxy for short-lived S3 presigned URLs of public template
 * assets. The browser cannot `fetch()` those URLs directly because the S3
 * bucket isn't configured with CORS for our origin — `<img>` and `<video>`
 * elements work fine (CORS isn't required for media tags) but reading the
 * bytes into a Blob/File for re-upload as a start frame / reference image
 * is blocked.
 *
 * Security model:
 *   - GET only.
 *   - Strict hostname allowlist (S3 + the bucket's CloudFront/CDN if any).
 *   - The presigned URL itself is the authorization — the public templates
 *     feed is unauthenticated by design, so we don't add a NextAuth gate on
 *     top of it. The allowlist prevents this route from being used as an
 *     open proxy to arbitrary hosts.
 *   - 25 MB upstream cap.
 */

import { NextRequest, NextResponse } from "next/server";

// Don't statically cache this route handler; presigned URLs rotate.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const ALLOWED_HOST_SUFFIXES = [
  ".amazonaws.com", // s3, s3.<region>.amazonaws.com, <bucket>.s3.amazonaws.com, etc.
  ".cloudfront.net", // CloudFront distributions sitting in front of S3.
] as const;
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

function errorResponse(status: number, code: string, detail?: string) {
  console.warn("[template-asset-proxy]", status, code, detail ?? "");
  return NextResponse.json({ error: code, detail: detail ?? null }, { status });
}

export async function GET(request: NextRequest) {
  const raw = request.nextUrl.searchParams.get("url");
  if (!raw) {
    return errorResponse(400, "missing_url");
  }

  const target = isAllowedAssetUrl(raw);
  if (!target) {
    let host = "<unparseable>";
    try {
      host = new URL(raw).hostname;
    } catch {
      /* ignore */
    }
    return errorResponse(403, "host_not_allowed", host);
  }

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), {
      method: "GET",
      redirect: "follow",
      // Don't forward cookies — the URL is already presigned.
      headers: { Accept: "image/*,video/*;q=0.9,*/*;q=0.5" },
      // Belt-and-suspenders: avoid Next's fetch dedupe / static cache.
      cache: "no-store",
    });
  } catch (err) {
    return errorResponse(
      502,
      "upstream_fetch_threw",
      err instanceof Error ? err.message : String(err),
    );
  }

  if (!upstream.ok) {
    return errorResponse(
      upstream.status,
      "upstream_non_ok",
      `${target.hostname} ${upstream.status}`,
    );
  }

  // Buffer the response — streaming the original body through NextResponse
  // is fragile when there's a reverse proxy in front of the Next server.
  // Template assets are bounded (25 MB), so the memory hit is acceptable.
  let buffer: ArrayBuffer;
  try {
    buffer = await upstream.arrayBuffer();
  } catch (err) {
    return errorResponse(
      502,
      "upstream_body_read_failed",
      err instanceof Error ? err.message : String(err),
    );
  }
  if (buffer.byteLength === 0) {
    return errorResponse(502, "upstream_empty_body");
  }
  if (buffer.byteLength > MAX_UPSTREAM_BYTES) {
    return errorResponse(
      413,
      "asset_too_large",
      String(buffer.byteLength),
    );
  }

  const contentType =
    upstream.headers.get("content-type") || "application/octet-stream";

  return new NextResponse(buffer, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Content-Length": String(buffer.byteLength),
      // Short cache so a quick second visit during the same edit session is
      // instant, but presigned URLs change so we don't cache for long.
      "Cache-Control": "private, max-age=120",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
