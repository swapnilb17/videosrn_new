/** Server-side calls to FastAPI /internal/* routes. */

export const INTERNAL_BACKEND_URL =
  process.env.INTERNAL_BACKEND_URL || "http://backend:8000";

/** Headers required by the backend when INTERNAL_API_SECRET is set. */
export function internalBackendHeaders(
  extra?: Record<string, string>,
): Record<string, string> {
  const secret = (process.env.INTERNAL_API_SECRET || "").trim();
  const h: Record<string, string> = { ...(extra || {}) };
  if (secret) {
    h["x-internal-api-key"] = secret;
  }
  return h;
}
