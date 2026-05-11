/**
 * Helpers for the Templates "Remix" flow: fetch a template's S3 presigned
 * asset via the same-origin proxy and hand it to a creator panel as a `File`
 * so it can be re-uploaded as a start frame / reference image.
 *
 * Why a proxy? See `app/api/template-asset-proxy/route.ts` — the S3 bucket
 * doesn't allow cross-origin `fetch()` even though `<img>` / `<video>` work.
 */

const PROXY_PATH = "/api/template-asset-proxy";

function extensionFromMime(mime: string): string {
  if (!mime) return "jpg";
  if (mime.includes("png")) return "png";
  if (mime.includes("webp")) return "webp";
  if (mime.includes("gif")) return "gif";
  return "jpg";
}

/**
 * Fetch a template asset (image) via the same-origin proxy and wrap it in a
 * `File` ready to be appended to a multipart form. Returns `null` on any
 * failure — callers should fall back to prompt-only mode without throwing.
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
  } catch {
    return null;
  }
  if (!res.ok) return null;
  let blob: Blob;
  try {
    blob = await res.blob();
  } catch {
    return null;
  }
  // Reject obviously-not-an-image responses so we don't stuff a video into the
  // image upload slot.
  const type = blob.type || "image/jpeg";
  if (!type.startsWith("image/")) return null;

  const ext = extensionFromMime(type);
  const safeBase = filenameBase.replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 60);
  return new File([blob], `${safeBase || "template"}.${ext}`, { type });
}
