/**
 * Helpers for the Templates "Remix" flow: pull a template's bytes from the
 * backend (which fetches them straight from S3 with its own credentials)
 * and hand them to a creator panel as a `File` so they can be re-uploaded
 * as a start frame / reference image.
 *
 * Why the backend (and not the presigned URL)?
 *   - The S3 bucket isn't CORS-configured for our origin, so the browser
 *     can't `fetch()` the presigned URL directly even though `<img>` /
 *     `<video>` tags work.
 *   - The dashboard's nginx layer routes `/api/templates/*` straight to
 *     FastAPI, so a Next.js route handler in that namespace is never hit.
 *     The clean path is the existing `/api/templates/{id}/asset` backend
 *     route, which streams the object bytes through.
 */

export type TemplateAssetVariant = "image" | "thumbnail";

function backendAssetUrl(
  templateId: string,
  variant: TemplateAssetVariant,
): string {
  const v = variant === "thumbnail" ? "thumbnail" : "image";
  return `/api/templates/${encodeURIComponent(templateId)}/asset?variant=${v}`;
}

function inferImageMimeFromBlob(blobType: string | undefined): string {
  if (blobType && blobType.startsWith("image/")) return blobType;
  return "image/jpeg";
}

function extensionForMime(mime: string): string {
  if (mime.includes("png")) return "png";
  if (mime.includes("webp")) return "webp";
  if (mime.includes("gif")) return "gif";
  if (mime.includes("bmp")) return "bmp";
  return "jpg";
}

/**
 * Fetch a template's bytes via the backend asset endpoint and wrap them in
 * a `File` ready to be appended to a multipart form. Returns `null` on any
 * failure — callers should fall back to prompt-only mode without throwing.
 *
 * `variant` defaults to `image` for image templates and should be
 * `thumbnail` for video templates so we get a still frame.
 */
export async function loadTemplateAsImageFile(
  templateId: string,
  variant: TemplateAssetVariant,
  filenameBase: string,
): Promise<File | null> {
  if (!templateId) return null;
  const url = backendAssetUrl(templateId, variant);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "GET",
      credentials: "include",
    });
  } catch (err) {
    if (typeof console !== "undefined") {
      console.error("[remix] backend asset fetch failed", err);
    }
    return null;
  }
  if (!res.ok) {
    let body = "";
    try {
      body = await res.text();
    } catch {
      /* ignore */
    }
    if (typeof console !== "undefined") {
      console.error(
        `[remix] backend returned ${res.status} for ${url}`,
        body,
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
      console.error("[remix] backend returned empty body");
    }
    return null;
  }

  const mime = inferImageMimeFromBlob(blob.type);
  // Re-wrap so downstream consumers see a proper image MIME even if the
  // upstream content-type was empty.
  const typed = new Blob([blob], { type: mime });
  const ext = extensionForMime(mime);
  const safeBase =
    filenameBase.replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 60) || "template";
  return new File([typed], `${safeBase}.${ext}`, { type: mime });
}
