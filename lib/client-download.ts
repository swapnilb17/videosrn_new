/**
 * Same-origin /media/* downloads: use Next.js proxy so the server follows
 * redirects to S3 (browser fetch would fail CORS on the presigned URL).
 */
function mediaPathForProxy(raw: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    const u = new URL(raw, window.location.origin);
    if (u.origin !== window.location.origin) return null;
    const path = u.pathname + u.search;
    return path.startsWith("/media/") ? path : null;
  } catch {
    return null;
  }
}

async function downloadViaSameOriginProxy(path: string, filename: string): Promise<void> {
  const trimmed = path.replace(/^\/+/, "");
  const qs = new URLSearchParams({ filename });
  const res = await fetch(
    `/api/download-proxy/${encodeURI(trimmed)}?${qs.toString()}`,
    {
      method: "GET",
      credentials: "include",
    },
  );
  if (!res.ok) {
    let detail = `Download failed (${res.status})`;
    try {
      const j = (await res.json()) as { error?: string };
      if (typeof j.error === "string") detail = j.error;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
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

/**
 * Trigger a browser file download. For /media/* on this origin, uses a server
 * proxy to avoid S3 CORS issues after redirect.
 */
export async function downloadUrlAsFile(
  url: string,
  filename: string,
): Promise<void> {
  const proxyPath = mediaPathForProxy(url);
  if (proxyPath) {
    await downloadViaSameOriginProxy(proxyPath, filename);
    return;
  }

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
