"use client";

import { useCallback, useRef, useState } from "react";
import {
  ImageIcon,
  Sparkles,
  RatioIcon,
  Grid3X3,
  Download,
  Loader2,
  Palette,
  Upload,
  X,
  User,
} from "lucide-react";
import { ClayButton } from "@/components/clay-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { generateImage, type GenerateImageResponse } from "@/lib/api";

const TEXT_STYLES = [
  { value: "photorealistic", label: "Photorealistic", icon: "📷" },
  { value: "cinematic", label: "Cinematic", icon: "🎬" },
  { value: "illustration", label: "Illustration", icon: "🎨" },
  { value: "3d_render", label: "3D Render", icon: "🧊" },
  { value: "anime", label: "Anime", icon: "✨" },
  { value: "watercolor", label: "Watercolor", icon: "🖌️" },
] as const;

const PORTRAIT_TEMPLATES = [
  { value: "ink_sketch", label: "Ink Sketch", thumb: "/templates/ink_sketch.jpg" },
  { value: "bold_text", label: "Bold Text", thumb: "/templates/bold_text.jpg" },
  { value: "street_art", label: "Street Art", thumb: "/templates/street_art.jpg" },
  { value: "sticky_notes", label: "Sticky Notes", thumb: "/templates/sticky_notes.jpg" },
  { value: "polaroid", label: "Polaroid", thumb: "/templates/polaroid.jpg" },
  { value: "cinematic_portrait", label: "Cinematic", thumb: "/templates/cinematic_portrait.jpg" },
  { value: "monochrome", label: "Monochrome", thumb: "/templates/monochrome.jpg" },
  { value: "color_block", label: "Color Block", thumb: "/templates/color_block.jpg" },
  { value: "runway", label: "Runway", thumb: "/templates/runway.jpg" },
  { value: "risograph", label: "Risograph", thumb: "/templates/risograph.jpg" },
  { value: "technicolor", label: "Technicolor", thumb: "/templates/technicolor.jpg" },
  { value: "gothic_clay", label: "Gothic Clay", thumb: "/templates/gothic_clay.jpg" },
  { value: "dynamite", label: "Dynamite", thumb: "/templates/dynamite.jpg" },
  { value: "steampunk", label: "Steampunk", thumb: "/templates/steampunk.jpg" },
  { value: "sunrise", label: "Sunrise", thumb: "/templates/sunrise.jpg" },
  { value: "satou", label: "Satou", thumb: "/templates/satou.jpg" },
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

const ACCEPTED_IMAGE_TYPES = "image/jpeg,image/png,image/webp";
const MAX_IMAGE_SIZE = 10 * 1024 * 1024; // 10 MB

export function TextToImage() {
  const [prompt, setPrompt] = useState("");
  const [style, setStyle] = useState("photorealistic");
  const [aspect, setAspect] = useState("1:1");
  const [count, setCount] = useState<number>(1);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateImageResponse | null>(null);

  const [uploadedImage, setUploadedImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageSelect = useCallback((file: File | null) => {
    if (!file) {
      setUploadedImage(null);
      setImagePreview(null);
      setSelectedTemplate(null);
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      setError("Image must be under 10 MB");
      return;
    }
    setUploadedImage(file);
    const url = URL.createObjectURL(file);
    setImagePreview(url);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0];
      if (file && file.type.startsWith("image/")) handleImageSelect(file);
    },
    [handleImageSelect],
  );

  const handleTemplateClick = useCallback(
    (templateValue: string) => {
      setSelectedTemplate(templateValue);
      setStyle(templateValue);
      const tpl = PORTRAIT_TEMPLATES.find((t) => t.value === templateValue);
      if (tpl) {
        setPrompt(
          `${tpl.label} style portrait — dramatic, celebrity quality, professional`,
        );
      }
    },
    [],
  );

  const clearUpload = useCallback(() => {
    setUploadedImage(null);
    setImagePreview(null);
    setSelectedTemplate(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

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
    if (uploadedImage) {
      fd.append("image", uploadedImage);
    }

    try {
      const res = await generateImage(fd);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Image generation failed");
    } finally {
      setGenerating(false);
    }
  }

  const hasPhoto = !!uploadedImage;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Text to Image</h1>

      <div className="grid gap-4 xl:grid-cols-[420px_1fr]">
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

          {/* Photo Upload */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <User className="h-4 w-4" /> Upload Your Photo{" "}
              <span className="text-slate-500 text-xs">(optional)</span>
            </label>

            {!imagePreview ? (
              <div
                className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-white/15 bg-[#0d1020] p-6 text-center cursor-pointer hover:border-purple-400/40 transition"
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="h-8 w-8 text-slate-500" />
                <p className="text-xs text-slate-400">
                  Drag & drop or click to upload your photo
                </p>
                <p className="text-[10px] text-slate-600">
                  JPG, PNG or WebP — max 10 MB
                </p>
              </div>
            ) : (
              <div className="relative rounded-xl overflow-hidden border border-white/15">
                <img
                  src={imagePreview}
                  alt="Uploaded"
                  className="w-full h-36 object-cover"
                />
                <button
                  onClick={clearUpload}
                  className="absolute top-2 right-2 rounded-full bg-black/60 p-1 hover:bg-black/80 transition"
                >
                  <X className="h-4 w-4 text-white" />
                </button>
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_IMAGE_TYPES}
              className="hidden"
              onChange={(e) => handleImageSelect(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Portrait Style Templates — shown when photo is uploaded */}
          {hasPhoto && (
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-sm text-slate-300">
                <Sparkles className="h-4 w-4" /> Pick a Style Template
              </label>
              <div className="grid grid-cols-4 gap-1.5">
                {PORTRAIT_TEMPLATES.map((tpl) => (
                  <button
                    key={tpl.value}
                    onClick={() => handleTemplateClick(tpl.value)}
                    className={`group relative flex flex-col items-center rounded-xl border overflow-hidden text-xs transition hover:border-purple-400/60 ${
                      selectedTemplate === tpl.value
                        ? "border-purple-400 ring-2 ring-purple-400/40"
                        : "border-white/10"
                    }`}
                  >
                    <img
                      src={tpl.thumb}
                      alt={tpl.label}
                      className="w-full aspect-square object-cover"
                    />
                    <span
                      className={`w-full text-center py-1.5 text-[11px] truncate px-1 ${
                        selectedTemplate === tpl.value
                          ? "bg-purple-500/20 text-white font-medium"
                          : "bg-[#0d1020] text-slate-400"
                      }`}
                    >
                      {tpl.label}
                    </span>
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-slate-600">
                Selecting a template auto-fills the prompt — feel free to edit it
              </p>
            </div>
          )}

          {/* Style dropdown — shown when NO photo is uploaded */}
          {!hasPhoto && (
            <div className="space-y-1.5">
              <label className="flex items-center gap-1.5 text-sm text-slate-300">
                <Palette className="h-4 w-4" /> Style
              </label>
              <select
                className={INPUT_CLS}
                value={style}
                onChange={(e) => setStyle(e.target.value)}
              >
                {TEXT_STYLES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.icon} {s.label}
                  </option>
                ))}
              </select>
            </div>
          )}

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
                {hasPhoto ? "Generate Portrait" : "Generate Images"}
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
                {hasPhoto
                  ? "Upload your photo, pick a style template, and click Generate Portrait to create your AI portrait."
                  : "Describe your image, choose a style, and click Generate Images to create AI images."}
              </p>
            </div>
          )}

          {/* During generation */}
          {generating && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-emerald-500/10 via-blue-500/5 to-orange-400/5 p-12 text-center min-h-[300px]">
              <Loader2 className="h-12 w-12 text-emerald-400 animate-spin mb-4" />
              <p className="text-slate-300 font-medium">
                {hasPhoto ? "Creating your portrait..." : "Creating your images..."}
              </p>
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
