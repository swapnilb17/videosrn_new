"use client";

import { useRef, useState } from "react";
import {
  Megaphone,
  Upload,
  X,
  Film,
  Timer,
  Monitor,
  Type,
  Palette,
  ImagePlus,
  Download,
  Loader2,
  LayoutTemplate,
  Gauge,
} from "lucide-react";
import { ClayButton } from "@/components/clay-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";
import {
  appendCreditIdentity,
  imageToAdVideo,
  type ImageToAdResponse,
} from "@/lib/api";

const AD_TEMPLATES = [
  { value: "product_showcase", label: "Product Showcase" },
  { value: "before_after", label: "Before / After" },
  { value: "feature_highlight", label: "Feature Highlight" },
  { value: "testimonial", label: "Testimonial" },
  { value: "sale_promo", label: "Sale / Promo" },
] as const;

const DURATIONS = [
  { value: 15, label: "15s" },
  { value: 30, label: "30s" },
  { value: 45, label: "45s" },
  { value: 60, label: "60s" },
] as const;

const ASPECTS = [
  { value: "16:9", label: "16:9" },
  { value: "9:16", label: "9:16" },
  { value: "1:1", label: "1:1" },
] as const;

const VIDEO_TIERS = [
  { value: "720", label: "Veo 3.1 Lite (720p)" },
  { value: "1080", label: "Veo 3.1 Lite (1080p)" },
] as const;

const INPUT_CLS =
  "w-full rounded-xl border border-white/15 bg-[#0d1020] p-2.5 text-sm outline-none transition focus:ring-2 focus:ring-purple-400/40";

export function ImageToAdVideo() {
  const { userEmail, userId } = useAuth();
  const productRef = useRef<HTMLInputElement>(null);
  const logoRef = useRef<HTMLInputElement>(null);
  const [productImage, setProductImage] = useState<File | null>(null);
  const [productPreview, setProductPreview] = useState<string | null>(null);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [adCopy, setAdCopy] = useState("");
  const [ctaText, setCtaText] = useState("");
  const [template, setTemplate] = useState("product_showcase");
  const [duration, setDuration] = useState(30);
  const [aspect, setAspect] = useState("9:16");
  const [brandColor, setBrandColor] = useState("#8b5cf6");
  const [videoTier, setVideoTier] = useState<(typeof VIDEO_TIERS)[number]["value"]>("1080");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImageToAdResponse | null>(null);

  function handleProductImage(file: File | null) {
    setProductImage(file);
    setProductPreview(file ? URL.createObjectURL(file) : null);
  }

  async function handleGenerate() {
    if (!productImage) return;
    setGenerating(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append("product_image", productImage);
    fd.append("ad_copy", adCopy.trim());
    fd.append("cta_text", ctaText.trim());
    fd.append("template", template);
    fd.append("duration", String(duration));
    fd.append("aspect_ratio", aspect);
    fd.append("brand_color", brandColor);
    if (logoFile) fd.append("logo", logoFile);
    fd.append("video_tier", videoTier);
    appendCreditIdentity(fd, userEmail, userId);

    try {
      const res = await imageToAdVideo(fd);
      setResult(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ad video generation failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Image to AD Video</h1>

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        {/* ========= LEFT PANEL — Controls ========= */}
        <Card className="space-y-4 overflow-y-auto max-h-[calc(100vh-140px)]">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Megaphone className="h-5 w-5 text-pink-400" />
            Ad Settings
          </h2>

          {/* Product image upload */}
          <div className="space-y-1.5">
            <label className="text-sm text-slate-300">Product Image</label>
            {productPreview ? (
              <div className="relative rounded-xl overflow-hidden border border-white/15">
                <img src={productPreview} alt="Product" className="w-full h-40 object-cover" />
                <button
                  type="button"
                  onClick={() => handleProductImage(null)}
                  className="absolute top-2 right-2 rounded-full bg-black/60 p-1 hover:bg-black/80 transition"
                >
                  <X className="h-4 w-4 text-white" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => productRef.current?.click()}
                className="flex w-full items-center gap-3 rounded-xl border-2 border-dashed border-white/15 bg-[#0d1020] px-4 py-6 text-slate-400 transition hover:border-pink-400/40 hover:text-slate-300"
              >
                <Upload className="h-5 w-5 shrink-0" />
                <div className="text-left">
                  <span className="text-sm block">Upload product image</span>
                  <span className="text-xs text-slate-500">JPG, PNG up to 10MB</span>
                </div>
              </button>
            )}
            <input
              ref={productRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => handleProductImage(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Ad template */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <LayoutTemplate className="h-4 w-4" /> Ad Template
            </label>
            <select
              className={INPUT_CLS}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            >
              {AD_TEMPLATES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          {/* Ad copy */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Type className="h-4 w-4" /> Ad Copy / Script
            </label>
            <textarea
              className={`${INPUT_CLS} h-20 resize-none`}
              placeholder="Your product is amazing because..."
              maxLength={500}
              value={adCopy}
              onChange={(e) => setAdCopy(e.target.value)}
            />
            <span className="block text-right text-xs text-slate-500">
              {adCopy.length}/500
            </span>
          </div>

          {/* CTA */}
          <div className="space-y-1.5">
            <label className="text-sm text-slate-300">Call to Action</label>
            <input
              type="text"
              className={INPUT_CLS}
              placeholder="Shop Now | Learn More | Get Started"
              value={ctaText}
              onChange={(e) => setCtaText(e.target.value)}
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

          {/* Aspect Ratio */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Monitor className="h-4 w-4" /> Format
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

          {/* Brand color */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <Palette className="h-4 w-4" /> Brand Color
            </label>
            <div className="flex items-center gap-2">
              <input
                type="color"
                value={brandColor}
                onChange={(e) => setBrandColor(e.target.value)}
                className="h-8 w-8 rounded-lg border border-white/15 bg-transparent cursor-pointer"
              />
              <span className="text-xs text-slate-500">{brandColor}</span>
            </div>
          </div>

          {/* Logo upload */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-sm text-slate-300">
              <ImagePlus className="h-4 w-4" /> Logo (optional)
            </label>
            {logoFile ? (
              <div className="flex items-center gap-2 rounded-xl border border-white/15 bg-[#0d1020] p-2 text-xs">
                <ImagePlus className="h-3.5 w-3.5 shrink-0 text-pink-400" />
                <span className="flex-1 truncate">{logoFile.name}</span>
                <button type="button" onClick={() => setLogoFile(null)} className="text-slate-400 hover:text-white">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => logoRef.current?.click()}
                className="flex w-full items-center gap-2 rounded-xl border border-dashed border-white/15 bg-[#0d1020] p-2 text-xs text-slate-400 transition hover:border-pink-400/40"
              >
                <Upload className="h-3.5 w-3.5" /> Upload logo
              </button>
            )}
            <input
              ref={logoRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(e) => setLogoFile(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Generate button */}
          <ClayButton
            className="w-full"
            onClick={handleGenerate}
            disabled={generating || !productImage}
          >
            {generating ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Creating Ad...
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <Film className="h-4 w-4" />
                Generate Ad Video
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
            <Monitor className="h-5 w-5 text-pink-400" />
            Preview
          </h2>

          {/* Before generation */}
          {!generating && !result && !error && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-pink-500/10 via-purple-500/5 to-rose-400/5 p-12 text-center min-h-[300px]">
              <Megaphone className="h-16 w-16 text-slate-500 mb-4" />
              <p className="text-slate-400 text-sm max-w-xs">
                Upload a product image, configure your ad, and click <strong>Generate Ad Video</strong> to create a promo.
              </p>
            </div>
          )}

          {/* During generation */}
          {generating && (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-gradient-to-br from-pink-500/10 via-purple-500/5 to-rose-400/5 p-12 text-center min-h-[300px]">
              <Loader2 className="h-12 w-12 text-pink-400 animate-spin mb-4" />
              <p className="text-slate-300 font-medium">Creating your ad with Veo 3.1 Lite...</p>
              <p className="text-slate-500 text-xs mt-1">
                This may take 2-5 minutes.
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
                  <span className="text-slate-500">Model</span>
                  <span className="text-slate-300">{result.model}</span>
                </span>
              </div>

              <a href={result.video_url} download className="block">
                <ClayButton className="w-full">
                  <span className="flex items-center gap-2">
                    <Download className="h-4 w-4" />
                    Download Ad Video
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
