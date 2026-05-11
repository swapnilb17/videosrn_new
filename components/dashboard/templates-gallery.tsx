"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { useIsTouch } from "@/lib/use-is-mobile";

type FeedItem = {
  id: string;
  kind: "image" | "video";
  title: string;
  description: string | null;
  category: string | null;
  language: string | null;
  content_type: string;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  tags: string[];
  url: string;
  thumbnail_url?: string | null;
};

type FeedResponse = { items: FeedItem[] };

type KindFilter = "all" | "image" | "video";

const REMIX_PROMPT_MAX = 800;

/** Snap a (width / height) ratio to a creator-supported aspect string.
 *  Returns `undefined` if the template doesn't carry usable dimensions —
 *  callers should then leave the existing default in place. */
function inferAspect(w: number | null, h: number | null): string | undefined {
  if (!w || !h || w <= 0 || h <= 0) return undefined;
  const r = w / h;
  if (r >= 1.5) return "16:9";
  if (r <= 0.7) return "9:16";
  if (Math.abs(r - 4 / 3) < 0.1) return "4:3";
  if (Math.abs(r - 1) < 0.1) return "1:1";
  return undefined;
}

/** Snap duration to the Photo-to-Video allowed values (4 / 6 / 8 seconds). */
function inferDuration(s: number | null): 4 | 6 | 8 | undefined {
  if (!s || s <= 0) return undefined;
  if (s <= 4) return 4;
  if (s <= 6) return 6;
  return 8;
}

/** Build a richer text-to-image prompt scaffold from template metadata.
 *  The Remix flow also seeds the *reference image*, so the prompt mostly
 *  needs to describe the subject + style and remind the model to match the
 *  reference. */
function buildImageRemixPrompt(t: FeedItem): string {
  const parts: string[] = [];
  if (t.title) parts.push(t.title.trim());
  if (t.description) parts.push(t.description.trim());
  if (t.tags && t.tags.length > 0) {
    parts.push(`Style: ${t.tags.slice(0, 6).join(", ")}`);
  }
  if (t.category) parts.push(`Category: ${t.category}`);
  parts.push(
    "High-quality, detailed, professional. Match the composition, lighting, and mood of the reference image.",
  );
  return parts.filter(Boolean).join(". ").slice(0, REMIX_PROMPT_MAX);
}

/** Build a *motion* prompt for the image-to-video remix flow. The visual
 *  itself is anchored by the template's first frame (start image), so the
 *  prompt focuses on motion + mood rather than describing what's in the
 *  scene. */
function buildVideoRemixPrompt(t: FeedItem, hasStartFrame: boolean): string {
  const parts: string[] = [];
  if (t.title) parts.push(`Animate "${t.title.trim()}".`);
  if (t.description) parts.push(t.description.trim());
  if (t.tags && t.tags.length > 0) {
    parts.push(`Mood: ${t.tags.slice(0, 6).join(", ")}`);
  }
  parts.push(
    hasStartFrame
      ? "Cinematic, subtle natural motion that matches the look and feel of the reference frame."
      : "Cinematic, professional, smooth camera motion in a polished short-form style.",
  );
  return parts.filter(Boolean).join(" ").slice(0, REMIX_PROMPT_MAX);
}

/** Build the creator URL for the Templates "Remix" flow.
 *  - Image templates → Text-to-Image with the template image as reference.
 *  - Video templates → Image-to-Video with the template's first frame as
 *    start frame (when a still URL is available). When no thumbnail exists
 *    we fall back to `text_to_video` so the user only needs to edit a
 *    prompt. */
function buildRemixHref(t: FeedItem): string {
  const params = new URLSearchParams();
  params.set("template_id", t.id);
  params.set("template_title", t.title);

  const aspect = inferAspect(t.width, t.height);
  if (aspect) params.set("aspect", aspect);

  if (t.kind === "video") {
    // For video remixes we need a *still* image as the start frame. The
    // `thumbnail_url` is a presigned still that the admin uploaded; if it's
    // missing, gracefully degrade to text-to-video.
    const startStill = t.thumbnail_url ?? null;
    params.set("service", "photo-to-video");
    if (startStill) {
      params.set("task", "image_to_video");
      params.set("asset_url", startStill);
    } else {
      params.set("task", "text_to_video");
    }
    params.set("prompt", buildVideoRemixPrompt(t, Boolean(startStill)));
    const duration = inferDuration(t.duration_seconds);
    if (duration) params.set("duration", String(duration));
  } else {
    // Image template → Text-to-Image with the template image as a reference.
    params.set("service", "text-to-image");
    params.set("prompt", buildImageRemixPrompt(t));
    if (t.url) params.set("asset_url", t.url);
  }
  return `/dashboard/create?${params.toString()}`;
}

export function TemplatesGallery() {
  const [items, setItems] = useState<FeedItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<KindFilter>("all");
  const [q, setQ] = useState("");

  useEffect(() => {
    let alive = true;
    setItems(null);
    setError(null);
    const params = new URLSearchParams({ limit: "60" });
    if (kind !== "all") params.set("kind", kind);
    fetch(`/api/templates/feed?${params.toString()}`, {
      method: "GET",
      cache: "no-store",
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as FeedResponse;
      })
      .then((data) => {
        if (alive) setItems(data.items ?? []);
      })
      .catch((e: unknown) => {
        if (alive) setError((e as Error).message || "failed to load templates");
      });
    return () => {
      alive = false;
    };
  }, [kind]);

  const filtered = useMemo(() => {
    if (!items) return null;
    const term = q.trim().toLowerCase();
    if (!term) return items;
    return items.filter((t) => {
      const hay = [
        t.title,
        t.description ?? "",
        t.category ?? "",
        t.language ?? "",
        (t.tags ?? []).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(term);
    });
  }, [items, q]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex overflow-hidden rounded-lg border border-white/10 text-xs">
          {(["all", "image", "video"] as KindFilter[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={
                "px-3 py-1.5 capitalize transition-colors " +
                (kind === k
                  ? "bg-purple-500/30 text-white"
                  : "text-slate-300 hover:bg-white/10")
              }
            >
              {k}
            </button>
          ))}
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search title, tag, category…"
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-purple-400 sm:ml-auto sm:w-64"
        />
      </div>

      {error ? (
        <div className="rounded-lg border border-rose-400/40 bg-rose-500/10 p-4 text-sm text-rose-200">
          Couldn&apos;t load templates: {error}
        </div>
      ) : items === null ? (
        <div className="text-sm text-slate-400">Loading templates…</div>
      ) : (filtered ?? items).length === 0 ? (
        <div className="rounded-lg border border-white/10 bg-white/5 p-6 text-sm text-slate-300">
          No templates available yet. Check back soon — new trending creatives
          are added regularly.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {(filtered ?? items).map((t) => (
            <TemplateCard key={t.id} t={t} />
          ))}
        </div>
      )}
    </div>
  );
}

function TemplateCard({ t }: { t: FeedItem }) {
  const isTouch = useIsTouch();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // On touch devices, hover doesn't exist — autoplay templates that are
  // mostly in view and pause the others. On mouse devices we keep the
  // hover-to-play affordance.
  useEffect(() => {
    if (!isTouch || t.kind !== "video") return;
    const node = videoRef.current;
    if (!node) return;
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            node.play().catch(() => {});
          } else {
            node.pause();
            node.currentTime = 0;
          }
        }
      },
      { threshold: 0.6 },
    );
    io.observe(node);
    return () => io.disconnect();
  }, [isTouch, t.kind]);

  const remixHref = buildRemixHref(t);
  const remixLabel = t.kind === "video" ? "Remix this video" : "Remix this image";

  return (
    <Link
      href={remixHref}
      aria-label={remixLabel}
      className="group relative block overflow-hidden rounded-xl border border-white/10 bg-white/5 transition-colors hover:border-purple-400/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-400"
    >
      <div className="relative aspect-[4/5] w-full overflow-hidden bg-black/40">
        {t.kind === "video" ? (
          // eslint-disable-next-line jsx-a11y/media-has-caption
          <video
            ref={videoRef}
            // Append #t=0.5 to coax the browser into showing a non-black
            // first frame even when the JPG poster hasn't loaded yet.
            src={`${t.url}#t=0.5`}
            poster={t.thumbnail_url ?? undefined}
            className="h-full w-full object-cover transition-transform group-hover:scale-[1.03]"
            muted
            loop
            playsInline
            preload="metadata"
            onMouseEnter={
              isTouch
                ? undefined
                : (e) => {
                    const v = e.currentTarget;
                    v.play().catch(() => {});
                  }
            }
            onMouseLeave={
              isTouch
                ? undefined
                : (e) => {
                    const v = e.currentTarget;
                    v.pause();
                    v.currentTime = 0;
                  }
            }
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={t.url}
            alt={t.title}
            className="h-full w-full object-cover transition-transform group-hover:scale-[1.03]"
            loading="lazy"
          />
        )}
        <span className="absolute left-2 top-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-200">
          {t.kind}
        </span>

        {/* Remix CTA — always visible on touch, hover-only on desktop */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-2 bottom-2 flex items-center justify-between gap-2 rounded-full border border-white/15 bg-black/65 px-3 py-1.5 text-xs font-medium text-white shadow-lg backdrop-blur-md transition-opacity md:opacity-0 md:group-hover:opacity-100"
        >
          <span className="flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-purple-300" />
            Remix
          </span>
          <ArrowRight className="h-3.5 w-3.5" />
        </div>
      </div>
      <div className="p-2.5">
        <div className="truncate text-sm font-medium text-slate-100" title={t.title}>
          {t.title}
        </div>
        <div className="mt-0.5 flex items-center gap-1 text-[11px] text-slate-400">
          {t.category ? <span>{t.category}</span> : null}
          {t.category && t.language ? <span>·</span> : null}
          {t.language ? <span className="uppercase">{t.language}</span> : null}
        </div>
      </div>
    </Link>
  );
}
