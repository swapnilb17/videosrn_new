"use client";

import { useRef, useState } from "react";
import {
  Upload,
  X,
  Camera,
  Timer,
  Move,
  Play,
  Download,
  Loader2,
  Monitor,
  Clapperboard,
  Gauge,
} from "lucide-react";
import { ClayButton } from "@/components/clay-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { appendCreditIdentity, photoToVideo, type PhotoToVideoResponse } from "@/lib/api";

const DURATIONS = [
  { value: 5, label: "5s" },
  { value: 8, label: "8s" },
  { value: 10, label: "10s" },
  { value: 15, label: "15s" },
] as const;

const CAMERA_MOVES = [
  { value: "pan_left", label: "Pan Left" },
  { value: "pan_right", label: "Pan Right" },
  { value: "zoom_in", label: "Zoom In" },
  { value: "zoom_out", label: "Zoom Out" },
  { value: "orbit", label: "Orbit" },
  { value: "dolly", label: "Dolly" },
  { value: "static", label: "Static" },
] as const;

const ASPECTS = [
  { value: "16:9", label: "16:9" },
  { value: "9:16", label: "9:16" },
  { value: "1:1", label: "1:1" },
] as const;

/** Backend video_tier + Vertex resolution (Veo 3.1 Lite). */
const VIDEO_TIERS = [
  { value: "720", label: "Veo 3.1 Lite (720p)" },
  { value: "1080", label: "Veo 3.1 Lite (1080p)" },
] as const;

const INPUT_CLS =
  "w-full rounded-xl border border-white/15 bg-[#0d1020] p-2.5 text-sm outline-none transition focus:ring-2 focus:ring-purple-400/40";

export function PhotoToVideo() {
  const { userEmail, userId } = useAuth();
  const fileRef = useRef<HTMLInputElement>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [motionPrompt, setMotionPrompt] = useState("");
  const [duration, setDuration] = useState(8);
  const [camera, setCamera] = useState("zoom_in");
  const [aspect, setAspect] = useState("16:9");
  const [videoTier, setVideoTier] = useState<(typeof VIDEO_TIERS)[number]["value"]>("1080");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PhotoToVideoResponse | null>(null);

  function handlePhoto(file: File | null) {
    setPhoto(file);
    setPhotoPreview(file ? URL.createObjectURL(file) : null);
  }

  async function handleGenerate() {
    if (!photo) return;
    setGenerating(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append("photo", photo);
    fd.append("motion_prompt", motionPrompt.trim());
    fd.append("duration", String(duration));
    fd.append("camera_movement", camera);
    fd.append("aspect_ratio", aspect);
    fd.append("video_tier", videoTier);
    appendCreditIdentity(fd, userEmail, userId);

    try {
      const res = await photoToVideo(fd);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Video generation failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Photo to Video</h1>

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        {/* ========= LEFT PANEL — Controls ========= */}
        <Card className="space-y-4 overflow-y-auto max-h-[calc(100vh-140px)]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Clapperboard className="h-5 w-5 text-blue-400" />
            Video Settings
          </h2>

          {/* Photo upload */}
          <div className="space-y-1.5">
            <label className="text-sm text-slate-300">Upload Photo</label>
            {photoPreview ? (
              <div className="relative rounded-xl overflow-hidden border border-white/15">
                <img src={photoPreview} alt="Upload" className="w-full h-40 object-cover" />
                <button
                  type="button"
                  onClick={() => handlePhoto(null)}
                  className="absolute top-2 right-2 rounded-full bg-black/60 p-1 hover:bg-black/80 transition"
                >
                  <X className="h-4 w-4 text-white" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="flex w-full items-center gap-3 rounded-xl border-2 border-dashed border-white/15 bg-[#0d1020] px-4 py-6 text-slate-400 transition hover:border-blue-400/40 hover:text-slate-300"
              >
                <Upload className="h-5 w-5 shrink-0" />
                <div className="text-left">
                  <span className="text-sm block">Click to upload a photo</span>
                  <span className="text-xs text-slate-500">JPG, PNG, WebP up to 10MB</span>
                </div>
              </button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handlePhoto(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Motion prompt */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Move className="h-4 w-4" /> Motion Description (optional)
            </label>
            <textarea
              className={`${INPUT_CLS} h-16 resize-none`}
              placeholder="Describe the motion (e.g., 'gentle breeze moves through hair')..."
              maxLength={300}
              value={motionPrompt}
              onChange={(e) => setMotionPrompt(e.target.value)}
            />
          </div>

          {/* Duration */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Timer className="h-4 w-4" /> Duration
            </label>
            <select
              className={INPUT_CLS}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            >
              {DURATIONS.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          {/* Camera Movement */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Camera className="h-4 w-4" /> Camera Movement
            </label>
            <select
              className={INPUT_CLS}
              value={camera}
              onChange={(e) => setCamera(e.target.value)}
            >
              {CAMERA_MOVES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          {/* Aspect Ratio */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Monitor className="h-4 w-4" /> Aspect Ratio
            </label>
            <select
              className={INPUT_CLS}
              value={aspect}
              onChange={(e) => setAspect(e.target.value)}
            >
              {ASPECTS.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>

          {/* Output resolution (Veo 3.1 Lite) */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Gauge className="h-4 w-4" /> Quality
            </label>
            <select
              className={INPUT_CLS}
              value={videoTier}
              onChange={(e) =>
                setVideoTier(e.target.value as (typeof VIDEO_TIERS)[number]["value"])
              }
            >
              {VIDEO_TIERS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          {/* Generate button */}
          <ClayButton
            className="w-full"
            onClick={handleGenerate}
            disabled={generating || !photo}
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Play className="h-4 w-4" />
                Generate Video
              </span>
            )}
          </ClayButton>

          <p className="text-xs text-slate-500">
            Powered by Google Veo 3.1 Lite on Vertex AI
          </p>
        </Card>

        {/* ========= RIGHT PANEL — Preview ========= */}
        <Card className="space-y-4 min-h-[400px]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Monitor className="h-5 w-5 text-blue-400" />
            Preview
          </h2>

          {/* Before generation */}
          {!generating && !result && !error && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-blue-500/10 via-cyan-500/5 to-purple-400/5 p-12 text-center min-h-[300px]">
              <Clapperboard className="h-16 w-16 text-slate-500 mb-4" />
              <p className="text-slate-400 text-sm max-w-xs">
                Upload a photo, choose settings, and click <strong>Generate Video</strong> to bring your image to life.
              </p>
            </div>
          )}

          {/* During generation */}
          {generating && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-blue-500/10 via-cyan-500/5 to-purple-400/5 p-12 text-center min-h-[300px]">
              <Loader2 className="h-12 w-12 text-blue-400 animate-spin mb-4" />
              <p className="text-slate-300 font-medium">Creating your video with Veo 3.1 Lite...</p>
              <p className="text-slate-500 text-xs mt-1">
                This may take 1-3 minutes.
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-center">
              <p className="text-red-400 font-medium mb-1">Generation Failed</p>
              <p className="text-sm text-red-300/80">{error}</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => setError(null)}
              >
                Dismiss
              </Button>
            </div>
          )}

          {/* Result */}
          {result && !generating && (
            <div className="space-y-4">
              <div className="rounded-2xl overflow-hidden border border-white/15 bg-black">
                <video src={result.video_url} controls className="w-full" />
              </div>

              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs">
                  <span className="text-slate-500">Duration</span>
                  <span className="text-slate-300">{result.duration_seconds}s</span>
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs">
                  <span className="text-slate-500">Size</span>
                  <span className="text-slate-300">{result.width}x{result.height}</span>
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs">
                  <span className="text-slate-500">Model</span>
                  <span className="text-slate-300">{result.model}</span>
                </span>
              </div>

              <a href={result.video_url} download className="block">
                <ClayButton className="w-full">
                  <span className="flex items-center gap-2">
                    <Download className="h-4 w-4" />
                    Download Video
                  </span>
                </ClayButton>
              </a>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
