"use client";

import { useState } from "react";
import {
  ImageIcon,
  Sparkles,
  RatioIcon,
  Grid3X3,
  Download,
  Loader2,
  Palette,
} from "lucide-react";
import { ClayButton } from "@/components/clay-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { generateImage, type GenerateImageResponse } from "@/lib/api";

const STYLES = [
  { value: "photorealistic", label: "Photorealistic", icon: "📷" },
  { value: "cinematic", label: "Cinematic", icon: "🎬" },
  { value: "illustration", label: "Illustration", icon: "🎨" },
  { value: "3d_render", label: "3D Render", icon: "🧊" },
  { value: "anime", label: "Anime", icon: "✨" },
  { value: "watercolor", label: "Watercolor", icon: "🖌️" },
] as const;

const ASPECTS = [
  { value: "1:1", label: "1:1" },
  { value: "16:9", label: "16:9" },
  { value: "9:16", label: "9:16" },
  { value: "4:3", label: "4:3" },
] as const;

const IMAGE_COUNTS = [1, 2, 4] as const;

const INPUT_CLS =
  "w-full rounded-xl border border-white/15 bg-[#0d1020] p-2.5 text-sm outline-none transition focus:ring-2 focus:ring-purple-400/40";

export function TextToImage() {
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("photorealistic");
  const [aspect, setAspect] = useState("1:1");
  const [count, setCount] = useState<number>(1);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateImageResponse | null>(null);

  async function handleGenerate() {
    if (!prompt.trim()) return;
    setGenerating(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append("prompt", prompt.trim());
    fd.append("style", style);
    fd.append("aspect_ratio", aspect);
    fd.append("count", String(count));

    try {
      const res = await generateImage(fd);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Image generation failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Text to Image</h1>

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        {/* ========= LEFT PANEL — Controls ========= */}
        <Card className="space-y-4 overflow-y-auto max-h-[calc(100vh-140px)]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <ImageIcon className="h-5 w-5 text-emerald-400" />
            Image Settings
          </h2>

          {/* Prompt */}
          <div className="space-y-1.5">
            <label className="text-sm text-slate-300">Describe your image</label>
            <textarea
              className={`${INPUT_CLS} h-28 resize-none`}
              placeholder="A futuristic city at sunset with flying cars..."
              maxLength={500}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <span className="block text-right text-xs text-slate-500">
              {prompt.length}/500
            </span>
          </div>

          {/* Style */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Palette className="h-4 w-4" /> Style
            </label>
            <select
              className={INPUT_CLS}
              value={style}
              onChange={(e) => setStyle(e.target.value)}
            >
              {STYLES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.icon} {s.label}
                </option>
              ))}
            </select>
          </div>

          {/* Aspect Ratio */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <RatioIcon className="h-4 w-4" /> Aspect Ratio
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

          {/* Image Count */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Grid3X3 className="h-4 w-4" /> Number of Images
            </label>
            <select
              className={INPUT_CLS}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
            >
              {IMAGE_COUNTS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          {/* Generate button */}
          <ClayButton
            className="w-full"
            onClick={handleGenerate}
            disabled={generating || !prompt.trim()}
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Sparkles className="h-4 w-4" />
                Generate Images
              </span>
            )}
          </ClayButton>

          <p className="text-xs text-slate-500">
            Powered by Gemini + Imagen (3-tier failover)
          </p>
        </Card>

        {/* ========= RIGHT PANEL — Preview ========= */}
        <Card className="space-y-4 min-h-[400px]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <ImageIcon className="h-5 w-5 text-emerald-400" />
            Preview
          </h2>

          {/* Before generation */}
          {!generating && !result && !error && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-emerald-500/10 via-blue-500/5 to-orange-400/5 p-12 text-center min-h-[300px]">
              <ImageIcon className="h-16 w-16 text-slate-500 mb-4" />
              <p className="text-slate-400 text-sm max-w-xs">
                Describe your image, choose a style, and click <strong>Generate Images</strong> to create AI images.
              </p>
            </div>
          )}

          {/* During generation */}
          {generating && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-emerald-500/10 via-blue-500/5 to-orange-400/5 p-12 text-center min-h-[300px]">
              <Loader2 className="h-12 w-12 text-emerald-400 animate-spin mb-4" />
              <p className="text-slate-300 font-medium">Creating your images...</p>
              <p className="text-slate-500 text-xs mt-1">
                This may take 10-30 seconds.
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
              <div className={`grid gap-3 ${result.images.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
                {result.images.map((img, i) => (
                  <div key={i} className="group relative rounded-xl overflow-hidden border border-white/15 bg-black">
                    <img src={img.url} alt={`Generated ${i + 1}`} className="w-full h-auto" />
                    <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                      <a href={img.url} download className="rounded-lg bg-white/20 backdrop-blur-sm p-2 hover:bg-white/30 transition">
                        <Download className="h-5 w-5 text-white" />
                      </a>
                    </div>
                    <div className="absolute bottom-2 left-2 rounded-full bg-black/60 backdrop-blur-sm px-2 py-0.5 text-[10px] text-slate-300">
                      {img.model}
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-slate-600">Prompt: {result.prompt_used}</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
