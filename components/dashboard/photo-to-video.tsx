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
  ImageIcon,
} from "lucide-react";
import { ClayButton } from "@/components/clay-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { downloadUrlAsFile, resolveMediaFilename } from "@/lib/client-download";
import { appendCreditIdentity, photoToVideo, type PhotoToVideoResponse } from "@/lib/api";

const DURATIONS = [
  { value: 4, label: "4s" },
  { value: 6, label: "6s" },
  { value: 8, label: "8s" },
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

const VIDEO_TIERS = [
  { value: "720", label: "720p" },
  { value: "1080", label: "1080p" },
] as const;

const TASKS = [
  { value: "text_to_video", label: "Text-to-video" },
  { value: "image_to_video", label: "Image-to-video" },
] as const;

const INPUT_CLS =
  "w-full rounded-xl border border-white/15 bg-[#0d1020] p-2.5 text-sm outline-none transition focus:ring-2 focus:ring-purple-400/40";

const FRAME_BOX =
  "flex flex-1 flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-white/15 bg-[#0d1020] px-3 py-8 text-center transition hover:border-blue-400/40";

export function PhotoToVideo() {
  const { userEmail, userId } = useAuth();
  const startRef = useRef<HTMLInputElement>(null);
  const endRef = useRef<HTMLInputElement>(null);
  const [task, setTask] = useState<(typeof TASKS)[number]["value"]>("image_to_video");
  const [startFrame, setStartFrame] = useState<File | null>(null);
  const [startPreview, setStartPreview] = useState<string | null>(null);
  const [endFrame, setEndFrame] = useState<File | null>(null);
  const [endPreview, setEndPreview] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(8);
  const [camera, setCamera] = useState("zoom_in");
  const [aspect, setAspect] = useState("16:9");
  const [videoTier, setVideoTier] = useState<(typeof VIDEO_TIERS)[number]["value"]>("1080");
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PhotoToVideoResponse | null>(null);

  const hasEndFrame = Boolean(endFrame);
  const imageMode = task === "image_to_video";

  function setStart(file: File | null) {
    setStartFrame(file);
    setStartPreview(file ? URL.createObjectURL(file) : null);
  }

  function setEnd(file: File | null) {
    setEndFrame(file);
    setEndPreview(file ? URL.createObjectURL(file) : null);
  }

  function canGenerate(): boolean {
    if (task === "text_to_video") return prompt.trim().length >= 3;
    return Boolean(startFrame);
  }

  async function handleDownloadVideo() {
    if (!result?.video_url) return;
    setDownloading(true);
    try {
      const name = resolveMediaFilename(
        result.video_url,
        `photo-to-video-${result.job_id}`,
        "mp4",
      );
      await downloadUrlAsFile(result.video_url, name);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  async function handleGenerate() {
    if (!canGenerate()) return;
    setGenerating(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append("task", task);
    fd.append("motion_prompt", prompt.trim());
    fd.append("duration", String(duration));
    fd.append("camera_movement", camera);
    fd.append("aspect_ratio", aspect);
    fd.append("video_tier", videoTier);
    if (imageMode && startFrame) fd.append("photo", startFrame);
    if (imageMode && endFrame) fd.append("end_photo", endFrame);
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
      <h1 className="text-2xl font-semibold">Image to Video</h1>

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card className="max-h-[calc(100vh-140px)] space-y-4 overflow-y-auto">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Clapperboard className="h-5 w-5 text-blue-400" />
            Veo 3.1 Lite
          </h2>

          <fieldset className="space-y-1.5 rounded-xl border border-sky-400/50 px-3 pb-3 pt-1">
            <legend className="px-1 text-xs font-medium text-sky-300/90">Task</legend>
            <select
              className={INPUT_CLS}
              value={task}
              onChange={(e) =>
                setTask(e.target.value as (typeof TASKS)[number]["value"])
              }
            >
              {TASKS.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </fieldset>

          <div className="space-y-1.5">
            <label className="text-sm text-slate-300">Prompt</label>
            <textarea
              className={`${INPUT_CLS} min-h-[88px] resize-y`}
              placeholder="Write your prompt…"
              maxLength={1200}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <p className="text-xs text-slate-500">
              {imageMode
                ? hasEndFrame
                  ? "Describe the motion between the start and end frames. Optional if you leave a default transition."
                  : "Optional for single-frame video; combines with camera movement below."
                : "Describe the scene and motion you want (required)."}
            </p>
          </div>

          {imageMode ? (
            <div className="space-y-1.5">
              <label className="text-sm text-slate-300">Input images</label>
              <div className="flex gap-3">
                <div className="min-w-0 flex-1">
                  {startPreview ? (
                    <div className="relative overflow-hidden rounded-xl border border-white/15">
                      <img
                        src={startPreview}
                        alt="Start frame"
                        className="h-36 w-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => setStart(null)}
                        className="absolute right-2 top-2 rounded-full bg-black/60 p-1 hover:bg-black/80"
                      >
                        <X className="h-4 w-4 text-white" />
                      </button>
                      <p className="bg-black/50 py-1 text-center text-xs text-white">Start</p>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => startRef.current?.click()}
                      className={FRAME_BOX}
                    >
                      <ImageIcon className="h-8 w-8 text-slate-400" />
                      <span className="text-sm text-slate-300">Start</span>
                    </button>
                  )}
                  <input
                    ref={startRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={(e) => setStart(e.target.files?.[0] ?? null)}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  {endPreview ? (
                    <div className="relative overflow-hidden rounded-xl border border-white/15 opacity-95">
                      <img
                        src={endPreview}
                        alt="End frame"
                        className="h-36 w-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => setEnd(null)}
                        className="absolute right-2 top-2 rounded-full bg-black/60 p-1 hover:bg-black/80"
                      >
                        <X className="h-4 w-4 text-white" />
                      </button>
                      <p className="bg-black/50 py-1 text-center text-xs text-slate-400">
                        End (optional)
                      </p>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => endRef.current?.click()}
                      className={`${FRAME_BOX} text-slate-500`}
                    >
                      <ImageIcon className="h-8 w-8 opacity-70" />
                      <span className="text-sm">End (optional)</span>
                    </button>
                  )}
                  <input
                    ref={endRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    onChange={(e) => setEnd(e.target.files?.[0] ?? null)}
                  />
                </div>
              </div>
            </div>
          ) : null}

          {imageMode && !hasEndFrame ? (
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-sm text-slate-300">
                <Camera className="h-4 w-4" /> Camera movement
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
          ) : null}

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
            <p className="text-xs text-slate-500">Veo uses 4, 6, or 8 seconds.</p>
          </div>

          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Monitor className="h-4 w-4" /> Aspect ratio
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

          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Move className="h-4 w-4" /> Resolution
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

          <ClayButton
            className="w-full"
            onClick={() => void handleGenerate()}
            disabled={generating || !canGenerate()}
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating…
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Play className="h-4 w-4" />
                Generate video
              </span>
            )}
          </ClayButton>

          <p className="text-xs text-slate-500">
            Image-to-video with start + end uses Veo first-and-last-frame generation on Vertex
            AI (same service account as other Veo calls).
          </p>
        </Card>

        <Card className="min-h-[400px] space-y-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Monitor className="h-5 w-5 text-blue-400" />
            Preview
          </h2>

          {!generating && !result && !error && (
            <div className="flex min-h-[300px] flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-blue-500/10 via-cyan-500/5 to-purple-400/5 p-12 text-center">
              <Clapperboard className="mb-4 h-16 w-16 text-slate-500" />
              <p className="max-w-xs text-sm text-slate-400">
                Choose <strong className="text-slate-300">Text-to-video</strong> or{" "}
                <strong className="text-slate-300">Image-to-video</strong>, set prompt and
                options, then generate.
              </p>
            </div>
          )}

          {generating && (
            <div className="flex min-h-[300px] flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-blue-500/10 via-cyan-500/5 to-purple-400/5 p-12 text-center">
              <Loader2 className="mb-4 h-12 w-12 animate-spin text-blue-400" />
              <p className="font-medium text-slate-300">Creating your video with Veo…</p>
              <p className="mt-1 text-xs text-slate-500">Often 1–3 minutes.</p>
            </div>
          )}

          {error && (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6 text-center">
              <p className="mb-1 font-medium text-red-400">Generation failed</p>
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

          {result && !generating && (
            <div className="space-y-4">
              <div className="overflow-hidden rounded-2xl border border-white/15 bg-black">
                <video src={result.video_url} controls className="w-full" />
              </div>

              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs">
                  <span className="text-slate-500">Duration</span>
                  <span className="text-slate-300">{result.duration_seconds}s</span>
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs">
                  <span className="text-slate-500">Size</span>
                  <span className="text-slate-300">
                    {result.width}×{result.height}
                  </span>
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs">
                  <span className="text-slate-500">Model</span>
                  <span className="text-slate-300">{result.model}</span>
                </span>
              </div>

              <ClayButton
                className="w-full"
                onClick={() => void handleDownloadVideo()}
                disabled={downloading}
              >
                <span className="flex items-center gap-2">
                  {downloading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  {downloading ? "Preparing download…" : "Download video"}
                </span>
              </ClayButton>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
