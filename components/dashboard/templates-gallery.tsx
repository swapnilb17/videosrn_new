"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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

  return (
    <div className="group relative overflow-hidden rounded-xl border border-white/10 bg-white/5 transition-colors hover:border-purple-400/50">
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
        <span className="absolute top-2 left-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-200">
          {t.kind}
        </span>
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
    </div>
  );
}
