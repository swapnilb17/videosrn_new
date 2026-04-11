/**
 * Trigger a browser file download. Prefer blob fetch so cross-origin redirects
 * (e.g. /media → S3 presigned URL) still save as a file instead of navigating away.
 */
export async function downloadUrlAsFile(
  url: string,
  filename: string,
): Promise<void> {
  const isAbsolute = /^https?:\/\//i.test(url);
  const init: RequestInit = {
    method: "GET",
    credentials: isAbsolute ? "omit" : "include",
  };

  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error("Network error while downloading. Try again.");
  }

  if (!res.ok) {
    throw new Error(`Download failed (${res.status})`);
  }

  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export function resolveMediaFilename(
  mediaUrl: string,
  fallbackBase: string,
  ext: string,
): string {
  try {
    const path = new URL(
      mediaUrl,
      typeof window !== "undefined" ? window.location.origin : "https://localhost",
    ).pathname;
    const seg = path.split("/").filter(Boolean).pop();
    if (seg && seg.includes(".")) return seg;
  } catch {
    /* ignore */
  }
  const safe = fallbackBase.replace(/[^a-zA-Z0-9._-]+/g, "-").slice(0, 80);
  return `${safe}.${ext}`;
}
