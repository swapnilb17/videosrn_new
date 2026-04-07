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
      detail = body.detail || detail;
    } catch {
      /* ignore parse failures */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export async function generateVideo(
  formData: FormData,
): Promise<GenerateResponse> {
  const res = await fetch("/generate", {
    method: "POST",
    body: formData,
    credentials: "include",
  });
  return handleResponse<GenerateResponse>(res);
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

export async function photoToVideo(fd: FormData): Promise<PhotoToVideoResponse> {
  const res = await fetch("/api/photo-to-video", { method: "POST", body: fd, credentials: "include" });
  return handleResponse<PhotoToVideoResponse>(res);
}

export type ImageToAdResponse = {
  job_id: string;
  video_url: string;
  duration_seconds: number;
  width: number;
  height: number;
  model: string;
};

export async function imageToAdVideo(fd: FormData): Promise<ImageToAdResponse> {
  const res = await fetch("/api/image-to-ad", { method: "POST", body: fd, credentials: "include" });
  return handleResponse<ImageToAdResponse>(res);
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
  const res = await fetch(`/api/user-media${qs}`, { credentials: "include" });
  const data = await handleResponse<{ items: MediaItemResponse[] }>(res);
  return data.items;
}
