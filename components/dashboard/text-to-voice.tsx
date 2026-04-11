"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Mic,
  Languages,
  Volume2,
  Play,
  Download,
  Loader2,
  Gauge,
} from "lucide-react";
import { ClayButton } from "@/components/clay-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import { downloadUrlAsFile, resolveMediaFilename } from "@/lib/client-download";
import {
  appendCreditIdentity,
  fetchVoices,
  ttsPreviewUrl,
  generateVoice,
  type VoiceInfo,
  type GenerateVoiceResponse,
} from "@/lib/api";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "mr", label: "Marathi" },
] as const;

const SPEEDS = [
  { value: 0.5, label: "0.5x" },
  { value: 0.75, label: "0.75x" },
  { value: 1.0, label: "1x" },
  { value: 1.25, label: "1.25x" },
  { value: 1.5, label: "1.5x" },
  { value: 2.0, label: "2x" },
] as const;

const INPUT_CLS =
  "w-full rounded-xl border border-white/15 bg-[#0d1020] p-2.5 text-sm outline-none transition focus:ring-2 focus:ring-purple-400/40";

export function TextToVoice() {
  const { userEmail, userId } = useAuth();
  const [text, setText] = useState("");
  const [language, setLanguage] = useState("en");
  const [voiceName, setVoiceName] = useState("");
  const [speed, setSpeed] = useState(1.0);
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateVoiceResponse | null>(null);
  const [previewSrc, setPreviewSrc] = useState<string | null>(null);

  async function handleDownloadAudio() {
    if (!result?.audio_url) return;
    setDownloading(true);
    try {
      const name = resolveMediaFilename(
        result.audio_url,
        `voice-${result.job_id}`,
        "mp3",
      );
      await downloadUrlAsFile(result.audio_url, name);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

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

  function handlePreview() {
    if (!voiceName) return;
    setPreviewSrc(ttsPreviewUrl(voiceName, language));
  }

  async function handleGenerate() {
    if (!text.trim()) return;
    setGenerating(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append("text", text.trim());
    fd.append("language", language);
    fd.append("speed", String(speed));
    if (voiceName) fd.append("voice", voiceName);
    appendCreditIdentity(fd, userEmail, userId);

    try {
      const res = await generateVoice(fd);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Voice generation failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Text to Voice</h1>

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        {/* ========= LEFT PANEL — Controls ========= */}
        <Card className="space-y-4 overflow-y-auto max-h-[calc(100vh-140px)]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Mic className="h-5 w-5 text-orange-400" />
            Voice Settings
          </h2>

          {/* Text */}
          <div className="space-y-1.5">
            <label className="text-sm text-slate-300">Text to speak</label>
            <textarea
              className={`${INPUT_CLS} h-32 resize-none`}
              placeholder="Enter the text you want to convert to speech..."
              maxLength={2000}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <span className="block text-right text-xs text-slate-500">
              {text.length}/2000
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
              <Volume2 className="h-4 w-4" /> Voice
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
                onClick={handlePreview}
                title="Preview voice"
              >
                <Play className="h-4 w-4" />
              </Button>
            </div>
            {previewSrc && (
              <audio
                key={previewSrc}
                src={previewSrc}
                controls
                autoPlay
                className="mt-1 w-full h-8"
              />
            )}
          </div>

          {/* Speed */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Gauge className="h-4 w-4" /> Speed
            </label>
            <select
              className={INPUT_CLS}
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            >
              {SPEEDS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          {/* Generate button */}
          <ClayButton
            className="w-full"
            onClick={handleGenerate}
            disabled={generating || !text.trim()}
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Mic className="h-4 w-4" />
                Generate Voice
              </span>
            )}
          </ClayButton>

          <p className="text-xs text-slate-500">
            Powered by Google TTS + ElevenLabs
          </p>
        </Card>

        {/* ========= RIGHT PANEL — Preview ========= */}
        <Card className="space-y-4 min-h-[400px]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Volume2 className="h-5 w-5 text-orange-400" />
            Preview
          </h2>

          {/* Before generation */}
          {!generating && !result && !error && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-orange-500/10 via-amber-500/5 to-red-400/5 p-12 text-center min-h-[300px]">
              <Volume2 className="h-16 w-16 text-slate-500 mb-4" />
              <p className="text-slate-400 text-sm max-w-xs">
                Enter your text, choose a voice, and click <strong>Generate Voice</strong> to create AI audio.
              </p>
            </div>
          )}

          {/* During generation */}
          {generating && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-orange-500/10 via-amber-500/5 to-red-400/5 p-12 text-center min-h-[300px]">
              <Loader2 className="h-12 w-12 text-orange-400 animate-spin mb-4" />
              <p className="text-slate-300 font-medium">Generating audio...</p>
              <p className="text-slate-500 text-xs mt-1">
                This may take a few seconds.
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
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-orange-500/20 shrink-0">
                    <Volume2 className="h-6 w-6 text-orange-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-200">Generated Audio</p>
                    <p className="text-xs text-slate-500">
                      {result.duration_seconds}s · {result.tts_provider} · {result.voice_used}
                    </p>
                  </div>
                </div>
                <audio src={result.audio_url} controls className="w-full" />
              </div>

              <ClayButton
                className="w-full"
                onClick={() => void handleDownloadAudio()}
                disabled={downloading}
              >
                <span className="flex items-center gap-2">
                  {downloading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  {downloading ? "Preparing download…" : "Download Audio"}
                </span>
              </ClayButton>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
