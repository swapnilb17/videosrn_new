export type GenerateResponse = {
  job_id: string;
  target_duration_seconds: number;
  script: {
    hook: string;
    facts: string[];
    ending: string;
    full_script_plain: string;
    visual_segments_en: string[];
    conversational_turns: { speaker: "male" | "female"; text: string }[];
  };
  mp3_url: string;
  mp4_url: string;
  video_width: number;
  video_height: number;
  content_format_applied: string | null;
  output_quality_applied: string | null;
  tts_provider: "google" | "elevenlabs" | "coqui";
  visual_mode: string;
  visual_detail: string | null;
  branding_logo_applied: boolean;
  product_image_applied: boolean;
  cta_image_applied: boolean;
  address_applied: boolean;
  thumbnail_attached: boolean;
};

export type VoiceInfo = {
  name: string;
  ssml_gender: string;
};

export type VoicesResponse = {
  available: boolean;
  language: string;
  locale: string | null;
  voices: VoiceInfo[];
  counts: { male: number; female: number; neutral: number; unspecified: number };
};

export type HealthResponse = {
  status: string;
  openai_ready: boolean;
  elevenlabs_ready: boolean;
  google_tts_ready: boolean;
  ffmpeg_ready: boolean;
  persistence_enabled: boolean;
  google_oauth_enabled: boolean;
  google_user_email: string | null;
  [key: string]: unknown;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail =
        (typeof body.detail === "string" && body.detail) ||
        (typeof body.error === "string" && body.error) ||
        detail;
    } catch {
      /* ignore parse failures */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export type JobStatusResponse = {
  job_id: string;
  status: "running" | "done" | "failed";
  error?: string;
  mp3_url?: string;
  mp4_url?: string;
  /** Veo standalone routes (photo-to-video, image-to-ad) mirror mp4_url for convenience. */
  video_url?: string;
  video_width?: number;
  video_height?: number;
  duration_seconds?: number;
  model?: string;
  tts_provider?: string;
  visual_mode?: string;
};

export async function submitVideoJob(
  formData: FormData,
): Promise<{ job_id: string }> {
  const res = await fetch("/generate", {
    method: "POST",
    body: formData,
    credentials: "include",
  });
  if (!res.ok && res.status !== 202) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<{ job_id: string }>;
}

export async function pollJobStatus(
  jobId: string,
): Promise<JobStatusResponse> {
  const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/status`, {
    credentials: "include",
  });
  return handleResponse<JobStatusResponse>(res);
}

export async function fetchVoices(
  language: string,
): Promise<VoicesResponse> {
  const res = await fetch(
    `/api/tts/voices?language=${encodeURIComponent(language)}`,
    { credentials: "include" },
  );
  return handleResponse<VoicesResponse>(res);
}

export function ttsPreviewUrl(voice: string, language: string): string {
  return `/api/tts/preview.mp3?voice=${encodeURIComponent(voice)}&language=${encodeURIComponent(language)}`;
}

export async function healthCheck(): Promise<HealthResponse> {
  const res = await fetch("/health", { credentials: "include" });
  return handleResponse<HealthResponse>(res);
}

export function mediaDownloadUrl(jobId: string): string {
  return `/media/${jobId}/output.mp4?attachment=true`;
}

/** Attach billing identity for FastAPI credit checks (1 credit = ₹1). */
export function appendCreditIdentity(
  fd: FormData,
  email: string,
  userSub?: string,
) {
  const em = (email || "").trim();
  if (em) fd.set("user_email", em);
  const s = (userSub || "").trim();
  if (s) fd.set("user_sub", s);
}

export type CreditsMeResponse = {
  credits_enabled: boolean;
  balance: number;
  plan: string;
  starter_redeem_available?: boolean;
};

export async function fetchCreditsMe(): Promise<CreditsMeResponse> {
  const res = await fetch("/api/credits/me", { credentials: "include" });
  return handleResponse<CreditsMeResponse>(res);
}

export async function redeemStarterCode(code: string): Promise<{
  ok: boolean;
  plan: string;
  balance: number;
}> {
  const res = await fetch("/api/credits/redeem", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
    credentials: "include",
  });
  return handleResponse(res);
}

export type CheckCreditCodeResponse = {
  ok?: boolean;
  valid: boolean;
  kind?: string;
  message?: string;
  credits?: number;
  credits_top_up?: number;
  target_balance?: number;
  already_used_globally?: boolean;
  already_used_on_account?: boolean;
  reason?: string;
};

export async function checkCreditCode(code: string): Promise<CheckCreditCodeResponse> {
  const res = await fetch("/api/credits/check-code", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
    credentials: "include",
  });
  return handleResponse<CheckCreditCodeResponse>(res);
}

export type GenerateImageResponse = {
  job_id: string;
  images: { url: string; width: number; height: number; model: string }[];
  prompt_used: string;
};

export async function generateImage(fd: FormData): Promise<GenerateImageResponse> {
  const res = await fetch("/api/generate-image", { method: "POST", body: fd, credentials: "include" });
  return handleResponse<GenerateImageResponse>(res);
}

export type GenerateVoiceResponse = {
  job_id: string;
  audio_url: string;
  duration_seconds: number;
  tts_provider: string;
  voice_used: string;
};

export async function generateVoice(fd: FormData): Promise<GenerateVoiceResponse> {
  const res = await fetch("/api/generate-voice", { method: "POST", body: fd, credentials: "include" });
  return handleResponse<GenerateVoiceResponse>(res);
}

export type PhotoToVideoResponse = {
  job_id: string;
  video_url: string;
  duration_seconds: number;
  width: number;
  height: number;
  model: string;
};

export type AsyncVeoJobAccepted = { job_id: string; status: string };

export async function submitPhotoToVideoJob(
  fd: FormData,
): Promise<AsyncVeoJobAccepted> {
  const res = await fetch("/api/photo-to-video", {
    method: "POST",
    body: fd,
    credentials: "include",
  });
  if (res.status === 202) {
    return res.json() as Promise<AsyncVeoJobAccepted>;
  }
  return handleResponse<AsyncVeoJobAccepted>(res);
}

export type ImageToAdResponse = {
  job_id: string;
  video_url: string;
  duration_seconds: number;
  width: number;
  height: number;
  model: string;
};

export async function submitImageToAdVideoJob(
  fd: FormData,
): Promise<AsyncVeoJobAccepted> {
  const res = await fetch("/api/image-to-ad", {
    method: "POST",
    body: fd,
    credentials: "include",
  });
  if (res.status === 202) {
    return res.json() as Promise<AsyncVeoJobAccepted>;
  }
  return handleResponse<AsyncVeoJobAccepted>(res);
}

// ---------------------------------------------------------------------------
// Media Library
// ---------------------------------------------------------------------------

export type MediaItemResponse = {
  id: string;
  media_type: "video" | "image" | "voice";
  title: string;
  media_url: string;
  thumbnail_url: string | null;
  source_service: string;
  extra: Record<string, unknown> | null;
  created_at: string | null;
};

export async function fetchUserMedia(
  type?: string,
): Promise<MediaItemResponse[]> {
  const qs = type ? `?type=${encodeURIComponent(type)}` : "";
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), 130_000);
  try {
    const res = await fetch(`/api/user-media${qs}`, {
      credentials: "include",
      signal: ac.signal,
    });
    const text = await res.text();
    let parsed: Record<string, unknown> = {};
    try {
      parsed = text ? (JSON.parse(text) as Record<string, unknown>) : {};
    } catch {
      const hint = text.trim().slice(0, 120);
      throw new ApiError(
        res.status,
        hint
          ? `Invalid JSON from Media Library: ${hint}`
          : `Invalid JSON from Media Library (HTTP ${res.status})`,
      );
    }
    if (!res.ok) {
      const detail =
        (typeof parsed.detail === "string" && parsed.detail) ||
        (typeof parsed.error === "string" && parsed.error) ||
        `HTTP ${res.status}`;
      throw new ApiError(res.status, detail);
    }
    const items = parsed.items;
    return Array.isArray(items) ? (items as MediaItemResponse[]) : [];
  } finally {
    clearTimeout(t);
  }
}
