"use client";

import { useEffect, useState } from "react";
import { Film, ImageIcon, Mic, Loader2, FolderOpen } from "lucide-react";
import { cn } from "@/lib/utils";
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
    "photo-to-video": "Photo to Video",
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

export function MediaGallery() {
  const [activeTab, setActiveTab] = useState("");
  const [items, setItems] = useState<MediaItemResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
            <a
              key={item.id}
              href={item.media_url}
              target="_blank"
              rel="noopener noreferrer"
              className="group overflow-hidden rounded-2xl border border-white/15 bg-white/5 transition hover:-translate-y-1 hover:bg-white/10"
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
                <span className="absolute right-2 top-2 rounded-full border border-white/15 bg-black/40 px-2 py-0.5 text-[10px] font-medium text-slate-200 backdrop-blur-sm">
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
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
