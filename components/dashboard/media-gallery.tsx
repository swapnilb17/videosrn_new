"use client";

import { useEffect, useState } from "react";
import { Film, ImageIcon, Mic, Loader2, FolderOpen, MoreVertical, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { downloadUrlAsFile, resolveMediaFilename } from "@/lib/client-download";
import { fetchUserMedia, type MediaItemResponse } from "@/lib/api";

const tabs = [
  { value: "", label: "All" },
  { value: "video", label: "Videos", icon: Film },
  { value: "image", label: "Images", icon: ImageIcon },
  { value: "voice", label: "Voice", icon: Mic },
] as const;

function serviceLabel(s: string) {
  const map: Record<string, string> = {
    "topic-to-video": "Topic to Video",
    "text-to-image": "Text to Image",
    "text-to-voice": "Text to Voice",
    "photo-to-video": "Image to Video",
    "image-to-ad": "Image to Ad",
  };
  return map[s] ?? s;
}

function relativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function mediaUrlOpenHref(raw: string): string {
  if (/^https?:\/\//i.test(raw)) return raw;
  if (typeof window === "undefined") return raw;
  return new URL(raw, window.location.origin).href;
}

export function MediaGallery() {
  const [activeTab, setActiveTab] = useState("");
  const [items, setItems] = useState<MediaItemResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [downloadBusyId, setDownloadBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    fetchUserMedia(activeTab || undefined)
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || "Failed to load media");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab]);

  useEffect(() => {
    if (!menuFor) return;
    const close = () => setMenuFor(null);
    const t = window.setTimeout(() => {
      document.addEventListener("click", close);
    }, 0);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("click", close);
    };
  }, [menuFor]);

  async function handleDownloadItem(item: MediaItemResponse) {
    const raw = (item.media_url || "").trim();
    if (!raw) return;
    setDownloadBusyId(item.id);
    try {
      const ext =
        item.media_type === "video"
          ? "mp4"
          : item.media_type === "voice"
            ? "mp3"
            : "png";
      const base = `${(item.title || "media").replace(/\s+/g, "-")}-${item.id.slice(0, 8)}`;
      const filename = resolveMediaFilename(raw, base, ext);
      await downloadUrlAsFile(raw, filename);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloadBusyId(null);
      setMenuFor(null);
    }
  }

  return (
    <div className="space-y-5">
      {/* Filter tabs */}
      <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-white/5 p-1 w-fit">
        {tabs.map((tab) => {
          const Icon = "icon" in tab ? tab.icon : null;
          return (
            <button
              key={tab.value}
              type="button"
              onClick={() => setActiveTab(tab.value)}
              className={cn(
                "flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition",
                activeTab === tab.value
                  ? "bg-purple-400/25 text-white shadow-[0_0_22px_rgba(142,119,255,0.35)]"
                  : "text-slate-300 hover:bg-white/10 hover:text-white",
              )}
            >
              {Icon && <Icon className="h-3.5 w-3.5" />}
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20 text-slate-400">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading media...
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && items.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-3 py-20 text-slate-400">
          <FolderOpen className="h-10 w-10" />
          <p className="text-sm">No media yet. Start generating to build your library.</p>
        </div>
      )}

      {/* Grid */}
      {!loading && !error && items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {items.map((item) => (
            <div
              key={item.id}
              className="group relative overflow-hidden rounded-2xl border border-white/15 bg-white/5 transition hover:-translate-y-1 hover:bg-white/10"
            >
              <button
                type="button"
                aria-label="Media actions"
                className="absolute right-2 top-2 z-20 flex h-8 w-8 items-center justify-center rounded-lg border border-white/15 bg-black/50 text-slate-200 backdrop-blur-sm transition hover:bg-black/70 hover:text-white"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setMenuFor((v) => (v === item.id ? null : item.id));
                }}
              >
                <MoreVertical className="h-4 w-4" />
              </button>

              {menuFor === item.id && (
                <div
                  className="absolute right-2 top-11 z-30 min-w-[10rem] overflow-hidden rounded-xl border border-white/15 bg-[#0f1424] py-1 text-xs shadow-xl"
                  onClick={(e) => e.stopPropagation()}
                  role="menu"
                >
                  <button
                    type="button"
                    role="menuitem"
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-200 hover:bg-white/10"
                    onClick={() => {
                      window.open(
                        mediaUrlOpenHref(item.media_url),
                        "_blank",
                        "noopener,noreferrer",
                      );
                      setMenuFor(null);
                    }}
                  >
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 opacity-70" />
                    Open in new tab
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    disabled={downloadBusyId === item.id || !item.media_url}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-slate-200 hover:bg-white/10 disabled:opacity-40"
                    onClick={() => void handleDownloadItem(item)}
                  >
                    {downloadBusyId === item.id ? (
                      <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                    ) : (
                      <span className="w-3.5 text-center">↓</span>
                    )}
                    Download
                  </button>
                </div>
              )}

              <button
                type="button"
                className="block w-full text-left"
                onClick={() =>
                  window.open(
                    mediaUrlOpenHref(item.media_url),
                    "_blank",
                    "noopener,noreferrer",
                  )
                }
              >
                {/* Thumbnail / type badge */}
                <div className="relative flex h-36 items-center justify-center bg-gradient-to-br from-purple-500/15 via-blue-500/10 to-white/5">
                  {item.media_type === "video" && (
                    <Film className="h-10 w-10 text-purple-300/60" />
                  )}
                  {item.media_type === "image" && item.media_url ? (
                    <img
                      src={item.media_url}
                      alt={item.title}
                      className="h-full w-full object-cover"
                    />
                  ) : item.media_type === "image" ? (
                    <ImageIcon className="h-10 w-10 text-blue-300/60" />
                  ) : null}
                  {item.media_type === "voice" && (
                    <Mic className="h-10 w-10 text-green-300/60" />
                  )}
                  <span className="pointer-events-none absolute left-2 top-2 rounded-full border border-white/15 bg-black/40 px-2 py-0.5 text-[10px] font-medium text-slate-200 backdrop-blur-sm">
                    {item.media_type}
                  </span>
                </div>

                <div className="space-y-1 p-3">
                  <p className="truncate text-sm font-medium text-slate-100 group-hover:text-white">
                    {item.title}
                  </p>
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>{serviceLabel(item.source_service)}</span>
                    {item.created_at && <span>{relativeTime(item.created_at)}</span>}
                  </div>
                </div>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
