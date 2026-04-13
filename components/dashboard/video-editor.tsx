"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Languages,
  Mic,
  Timer,
  Sparkles,
  Monitor,
  Gauge,
  ImagePlus,
  MapPin,
  Play,
  Download,
  Loader2,
  Volume2,
  Film,
  GalleryHorizontalEnd,
  Upload,
  X,
} from "lucide-react";
import { ClayButton } from "@/components/clay-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { downloadUrlAsFile } from "@/lib/client-download";
import {
  submitVideoJob,
  pollJobStatus,
  fetchVoices,
  ttsPreviewUrl,
  mediaDownloadUrl,
  appendCreditIdentity,
  type JobStatusResponse,
  type VoiceInfo,
} from "@/lib/api";

type VideoEditorProps = {
  title?: string;
};

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "mr", label: "Marathi" },
] as const;

const DURATIONS = [
  { value: 30, label: "30s" },
  { value: 59, label: "59s" },
  { value: 90, label: "90s" },
  { value: 120, label: "2 min" },
  { value: 180, label: "3 min" },
  { value: 240, label: "4 min" },
  { value: 300, label: "5 min" },
] as const;

const FORMATS = [
  { value: "youtube_landscape", label: "YouTube 16:9", aspect: "16:9" },
  { value: "reels_shorts", label: "Reels / Shorts 9:16", aspect: "9:16" },
  { value: "instagram_fb", label: "Instagram 1:1", aspect: "1:1" },
] as const;

const QUALITIES = [
  { value: "720p", label: "720p" },
  { value: "1080p", label: "1080p" },
  { value: "4k", label: "4K" },
  { value: "8k", label: "8K" },
] as const;

const INPUT_CLS =
  "w-full rounded-xl border border-white/15 bg-[#0d1020] p-2.5 text-sm outline-none transition focus:ring-2 focus:ring-purple-400/40";

/** After this many ms still generating, show Media Library hint (aligns with ~Cloudflare-scale waits). */
const LONG_WAIT_HINT_AFTER_MS = 90_000;

function FileUploadField({
  label,
  accept,
  file,
  onFileChange,
}: {
  label: string;
  accept: string;
  file: File | null;
  onFileChange: (f: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="space-y-1">
      <span className="text-xs text-slate-400">{label}</span>
      {file ? (
        <div className="flex items-center gap-2 rounded-xl border border-white/15 bg-[#0d1020] p-2 text-xs">
          <ImagePlus className="h-3.5 w-3.5 shrink-0 text-purple-400" />
          <span className="flex-1 truncate">{file.name}</span>
          <button
            type="button"
            onClick={() => onFileChange(null)}
            className="text-slate-400 hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full items-center gap-2 rounded-xl border border-dashed border-white/15 bg-[#0d1020] p-2 text-xs text-slate-400 transition hover:border-purple-400/40 hover:text-slate-300"
        >
          <Upload className="h-3.5 w-3.5" />
          Choose file
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

export function VideoEditor({ title = "Create Video" }: VideoEditorProps) {
  const { userEmail, userId } = useAuth();
  // --- Left panel state ---
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState("en");
  const [voiceName, setVoiceName] = useState("");
  const [duration, setDuration] = useState(59);
  const [enhanceMotion, setEnhanceMotion] = useState(false);

  // --- Right panel state ---
  const [contentFormat, setContentFormat] = useState("reels_shorts");
  const [outputQuality, setOutputQuality] = useState("1080p");
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [productFile, setProductFile] = useState<File | null>(null);
  const [ctaFile, setCtaFile] = useState<File | null>(null);
  const [thumbFile, setThumbFile] = useState<File | null>(null);
  const [address, setAddress] = useState("");

  // --- Voices ---
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [voicesLoading, setVoicesLoading] = useState(false);

  // --- Generation state ---
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<JobStatusResponse | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const longWaitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [longWaitHint, setLongWaitHint] = useState(false);

  // --- Preview audio ---
  const [previewAudioSrc, setPreviewAudioSrc] = useState<string | null>(null);

  const loadVoices = useCallback(async (lang: string) => {
    setVoicesLoading(true);
    try {
      const data = await fetchVoices(lang);
      setVoices(data.voices ?? []);
      setVoiceName("");
    } catch {
      setVoices([]);
    } finally {
      setVoicesLoading(false);
    }
  }, []);

  useEffect(() => {
    loadVoices(language);
  }, [language, loadVoices]);

  function handleVoicePreview() {
    if (!voiceName) return;
    setPreviewAudioSrc(ttsPreviewUrl(voiceName, language));
  }

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      if (longWaitTimerRef.current) clearTimeout(longWaitTimerRef.current);
    };
  }, []);

  async function handleDownloadVideo() {
    if (!result?.job_id) return;
    setDownloading(true);
    try {
      await downloadUrlAsFile(
        mediaDownloadUrl(result.job_id),
        `learncast-${result.job_id}.mp4`,
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  async function handleGenerate() {
    if (!topic.trim()) return;
    setGenerating(true);
    setError(null);
    setResult(null);
    setLongWaitHint(false);
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    if (longWaitTimerRef.current) {
      clearTimeout(longWaitTimerRef.current);
      longWaitTimerRef.current = null;
    }

    const fd = new FormData();
    fd.append("topic", topic.trim());
    fd.append("language", language);
    fd.append("target_duration_seconds", String(duration));
    fd.append("enhance_motion", enhanceMotion ? "true" : "false");
    if (voiceName) fd.append("google_tts_voice", voiceName);
    fd.append("content_format", contentFormat);
    fd.append("output_quality", outputQuality);
    if (logoFile) fd.append("logo", logoFile);
    if (productFile) fd.append("product_image", productFile);
    if (ctaFile) fd.append("cta_image", ctaFile);
    if (thumbFile) fd.append("thumbnail_image", thumbFile);
    if (address.trim()) fd.append("address", address.trim());
    appendCreditIdentity(fd, userEmail, userId);

    try {
      const { job_id } = await submitVideoJob(fd);

      longWaitTimerRef.current = setTimeout(() => {
        longWaitTimerRef.current = null;
        setLongWaitHint(true);
      }, LONG_WAIT_HINT_AFTER_MS);

      pollingRef.current = setInterval(async () => {
        try {
          const status = await pollJobStatus(job_id);
          if (status.status === "done") {
            if (pollingRef.current) clearInterval(pollingRef.current);
            pollingRef.current = null;
            if (longWaitTimerRef.current) {
              clearTimeout(longWaitTimerRef.current);
              longWaitTimerRef.current = null;
            }
            setLongWaitHint(false);
            setResult(status);
            setGenerating(false);
          } else if (status.status === "failed") {
            if (pollingRef.current) clearInterval(pollingRef.current);
            pollingRef.current = null;
            if (longWaitTimerRef.current) {
              clearTimeout(longWaitTimerRef.current);
              longWaitTimerRef.current = null;
            }
            setLongWaitHint(false);
            setError(status.error || "Generation failed");
            setGenerating(false);
          }
        } catch {
          // transient poll failure — keep trying
        }
      }, 4000);
    } catch (e: unknown) {
      if (longWaitTimerRef.current) {
        clearTimeout(longWaitTimerRef.current);
        longWaitTimerRef.current = null;
      }
      setLongWaitHint(false);
      const msg = e instanceof Error ? e.message : "Generation failed";
      setError(msg);
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{title}</h1>

      <div className="grid gap-4 xl:grid-cols-[320px_1fr_300px]">
        {/* ========= LEFT PANEL — Prompt & Controls ========= */}
        <Card className="space-y-4 overflow-y-auto max-h-[calc(100vh-140px)]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Film className="h-5 w-5 text-purple-400" />
            Prompt &amp; Controls
          </h2>

          {/* Topic */}
          <div className="space-y-1.5">
            <label className="text-sm text-slate-300">Topic</label>
            <textarea
              className={`${INPUT_CLS} h-28 resize-none`}
              placeholder="Enter your video topic (max 1000 characters)…"
              maxLength={1000}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
            <span className="block text-right text-xs text-slate-500">
              {topic.length}/1000
            </span>
          </div>

          {/* Language */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Languages className="h-4 w-4" /> Language
            </label>
            <select
              className={INPUT_CLS}
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          {/* Voice */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Mic className="h-4 w-4" /> Narration Voice
            </label>
            <div className="flex gap-2">
              <select
                className={`${INPUT_CLS} flex-1`}
                value={voiceName}
                onChange={(e) => setVoiceName(e.target.value)}
                disabled={voicesLoading}
              >
                <option value="">
                  {voicesLoading ? "Loading voices..." : "Auto-select"}
                </option>
                {voices.map((v) => (
                  <option key={v.name} value={v.name}>
                    {v.name} ({v.ssml_gender})
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                size="sm"
                disabled={!voiceName}
                onClick={handleVoicePreview}
                title="Preview voice"
              >
                <Volume2 className="h-4 w-4" />
              </Button>
            </div>
            {previewAudioSrc && (
              <audio
                key={previewAudioSrc}
                src={previewAudioSrc}
                controls
                autoPlay
                className="mt-1 w-full h-8"
              />
            )}
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

          {/* Enhance Motion */}
          <label className="flex items-center justify-between rounded-xl border border-white/10 bg-[#0f1325] p-3 text-sm cursor-pointer">
            <span className="flex items-center gap-1.5">
              <Sparkles className="h-4 w-4 text-amber-400" />
              Enhance Mode
            </span>
            <input
              type="checkbox"
              checked={enhanceMotion}
              onChange={(e) => setEnhanceMotion(e.target.checked)}
              className="h-4 w-4 accent-purple-500"
            />
          </label>
          <p className="text-xs text-slate-500 -mt-2 pl-1">
            Ken Burns zoom + two-voice conversational narration. Billing uses ~1.75
            credits/sec of target duration (rounded up); standard mode ~0.75/sec.
          </p>

          {/* Generate button */}
          <ClayButton
            className="w-full"
            onClick={handleGenerate}
            disabled={generating || !topic.trim()}
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
        </Card>

        {/* ========= CENTER PANEL — Preview ========= */}
        <Card className="space-y-4 min-h-[400px]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Monitor className="h-5 w-5 text-purple-400" />
            Preview
          </h2>

          {/* Before generation */}
          {!generating && !result && !error && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-purple-500/10 via-blue-500/5 to-orange-400/5 p-12 text-center min-h-[300px]">
              <Film className="h-16 w-16 text-slate-500 mb-4" />
              <p className="text-slate-400 text-sm max-w-xs">
                Fill in your topic, choose settings, and click <strong>Generate Video</strong> to create your AI video.
              </p>
            </div>
          )}

          {/* During generation */}
          {generating && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-purple-500/10 via-blue-500/5 to-orange-400/5 p-12 text-center min-h-[300px]">
              <Loader2 className="h-12 w-12 text-purple-400 animate-spin mb-4" />
              <p className="text-slate-300 font-medium">Generating your video...</p>
              <p className="text-slate-500 text-xs mt-1">
                This may take 2-5 minutes depending on duration and quality.
              </p>
              {longWaitHint && (
                <div className="mt-6 max-w-sm rounded-xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-left">
                  <p className="text-sm text-amber-100/90">
                    Video generation is taking longer than usual. You can keep this page open, or
                    check your{" "}
                    <Link
                      href="/dashboard/media"
                      className="font-medium text-amber-200 underline underline-offset-2 hover:text-white"
                    >
                      Media Library
                    </Link>{" "}
                    in the next few minutes — your video will appear there when it is ready.
                  </p>
                  <Link
                    href="/dashboard/media"
                    className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-amber-200/90 hover:text-white"
                  >
                    <GalleryHorizontalEnd className="h-3.5 w-3.5" />
                    Open Media Library
                  </Link>
                </div>
              )}
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
              {/* Video player */}
              <div className="rounded-2xl overflow-hidden border border-white/15 bg-black">
                <video
                  src={result.mp4_url}
                  controls
                  className="w-full"
                />
              </div>

              {/* Metadata badges */}
              <div className="flex flex-wrap gap-2">
                {result.tts_provider && <Badge label="TTS" value={result.tts_provider} />}
                {result.visual_mode && <Badge label="Visual" value={result.visual_mode.replace(/_/g, " ")} />}
                {result.video_width && result.video_height && (
                  <Badge label="Size" value={`${result.video_width}×${result.video_height}`} />
                )}
              </div>

              {/* Download */}
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
                  {downloading ? "Preparing download…" : "Download Video"}
                </span>
              </ClayButton>
            </div>
          )}
        </Card>

        {/* ========= RIGHT PANEL — Video Settings & Assets ========= */}
        <Card className="space-y-4 overflow-y-auto max-h-[calc(100vh-140px)]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Gauge className="h-5 w-5 text-purple-400" />
            Video Settings &amp; Assets
          </h2>

          {/* Format */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Monitor className="h-4 w-4" /> Format
            </label>
            <select
              className={INPUT_CLS}
              value={contentFormat}
              onChange={(e) => setContentFormat(e.target.value)}
            >
              {FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>

          {/* Quality */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Gauge className="h-4 w-4" /> Quality
            </label>
            <select
              className={INPUT_CLS}
              value={outputQuality}
              onChange={(e) => setOutputQuality(e.target.value)}
            >
              {QUALITIES.map((q) => (
                <option key={q.value} value={q.value}>
                  {q.label}
                </option>
              ))}
            </select>
          </div>

          {/* Divider */}
          <div className="border-t border-white/10 pt-2">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-3">
              Asset Uploads
            </p>
          </div>

          <FileUploadField
            label="Branding Logo (watermarked on every frame)"
            accept="image/png,image/jpeg,image/webp"
            file={logoFile}
            onFileChange={setLogoFile}
          />

          <FileUploadField
            label="Product Image (composited on slides)"
            accept="image/png,image/jpeg,image/webp"
            file={productFile}
            onFileChange={setProductFile}
          />

          <FileUploadField
            label="CTA Image (rendered as closing slide)"
            accept="image/png,image/jpeg,image/webp"
            file={ctaFile}
            onFileChange={setCtaFile}
          />

          <FileUploadField
            label="Thumbnail (attached as MP4 poster)"
            accept="image/png,image/jpeg,image/webp"
            file={thumbFile}
            onFileChange={setThumbFile}
          />

          {/* Address */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <MapPin className="h-4 w-4" /> Address Watermark
            </label>
            <input
              type="text"
              className={INPUT_CLS}
              placeholder="Business address (burned into overlay)"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}

function Badge({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-300">{value}</span>
    </span>
  );
}
