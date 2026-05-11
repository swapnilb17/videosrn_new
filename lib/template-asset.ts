/**
 * Helpers for the Templates "Remix" flow: fetch a template's S3 presigned
 * asset via the same-origin proxy and hand it to a creator panel as a `File`
 * so it can be re-uploaded as a start frame / reference image.
 *
 * Why a proxy? See `app/api/template-asset-proxy/route.ts` — the S3 bucket
 * doesn't allow cross-origin `fetch()` even though `<img>` / `<video>` work.
 */

const PROXY_PATH = "/api/template-asset-proxy";

/** Try the response Content-Type first, then the URL path extension, then
 *  fall back to JPEG. We never want to reject a real image just because S3
 *  served it with `application/octet-stream`. */
function inferImageMime(rawUrl: string, blobType: string | undefined): string {
  if (blobType && blobType.startsWith("image/")) return blobType;
  let pathname = "";
  try {
    pathname = new URL(rawUrl).pathname;
  } catch {
    pathname = rawUrl;
  }
  const ext = pathname.toLowerCase().match(/\.(jpe?g|png|webp|gif|bmp)(\?|$)/);
  if (!ext) return "image/jpeg";
  switch (ext[1]) {
    case "png":
      return "image/png";
    case "webp":
      return "image/webp";
    case "gif":
      return "image/gif";
    case "bmp":
      return "image/bmp";
    default:
      return "image/jpeg";
  }
}

function extensionForMime(mime: string): string {
  if (mime.includes("png")) return "png";
  if (mime.includes("webp")) return "webp";
  if (mime.includes("gif")) return "gif";
  if (mime.includes("bmp")) return "bmp";
  return "jpg";
}

/**
 * Fetch a template asset (image) via the same-origin proxy and wrap it in a
 * `File` ready to be appended to a multipart form. Returns `null` on any
 * failure — callers should fall back to prompt-only mode without throwing.
 *
 * This is intentionally permissive about content type: the template asset
 * URL came from our own trusted feed, so we don't need to defensively
 * reject responses with a generic MIME like `application/octet-stream`.
 */
export async function loadTemplateAssetAsImageFile(
  assetUrl: string,
  filenameBase: string,
): Promise<File | null> {
  if (!assetUrl) return null;
  const proxied = `${PROXY_PATH}?url=${encodeURIComponent(assetUrl)}`;
  let res: Response;
  try {
    res = await fetch(proxied, {
      method: "GET",
      credentials: "include",
    });
  } catch (err) {
    if (typeof console !== "undefined") {
      console.error("[remix] proxy fetch failed", err);
    }
    return null;
  }
  if (!res.ok) {
    if (typeof console !== "undefined") {
      console.error(
        "[remix] proxy returned non-OK status",
        res.status,
        await res.text().catch(() => ""),
      );
    }
    return null;
  }

  let blob: Blob;
  try {
    blob = await res.blob();
  } catch (err) {
    if (typeof console !== "undefined") {
      console.error("[remix] failed to read blob", err);
    }
    return null;
  }

  if (!blob || blob.size === 0) {
    if (typeof console !== "undefined") {
      console.error("[remix] proxy returned empty body");
    }
    return null;
  }

  const mime = inferImageMime(assetUrl, blob.type);
  // Re-wrap the blob with the inferred MIME so downstream consumers don't
  // see `application/octet-stream` or an empty type.
  const typed = new Blob([blob], { type: mime });
  const ext = extensionForMime(mime);
  const safeBase =
    filenameBase.replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 60) || "template";
  return new File([typed], `${safeBase}.${ext}`, { type: mime });
}
