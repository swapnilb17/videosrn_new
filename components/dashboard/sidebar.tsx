"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Home,
  FolderKanban,
  GalleryHorizontalEnd,
  Settings,
  Film,
  ImageIcon,
  Mic,
  Clapperboard,
  Megaphone,
} from "lucide-react";
import { cn } from "@/lib/utils";

const mainLinks = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/dashboard/media", label: "Media Library", icon: GalleryHorizontalEnd },
  { href: "/dashboard/projects", label: "Projects", icon: FolderKanban },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

const serviceLinks = [
  { service: "topic-to-video", label: "Topic to Video", icon: Film },
  { service: "text-to-image", label: "Text to Image", icon: ImageIcon },
  { service: "text-to-voice", label: "Text to Voice", icon: Mic },
  { service: "photo-to-video", label: "Image to Video", icon: Clapperboard },
  { service: "image-to-ad", label: "Image to AD Video", icon: Megaphone },
];

export function DashboardSidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeService = searchParams.get("service") ?? "topic-to-video";
  const isCreatePage = pathname === "/dashboard/create";

  return (
    <aside className="w-full border-b border-white/10 bg-[#0d1020] p-4 md:w-64 md:border-b-0 md:border-r">
      <Link href="/" className="mb-8 flex items-center gap-2 text-lg font-semibold">
        <Image
          src="/logo.png"
          alt="EnablyAI logo"
          width={24}
          height={24}
          className="rounded-md"
        />
        EnablyAI
      </Link>

      {/* Main nav */}
      <nav className="grid gap-1">
        {mainLinks.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-purple-500/20 text-white"
                  : "text-slate-300 hover:bg-white/10 hover:text-white",
              )}
            >
              <Icon className="h-4 w-4" />
              {link.label}
            </Link>
          );
        })}
      </nav>

      {/* Divider + AI Services */}
      <div className="mt-6 mb-3 border-t border-white/10 pt-4">
        <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          AI Services
        </p>
      </div>

      <nav className="grid gap-1">
        {serviceLinks.map((svc) => {
          const Icon = svc.icon;
          const isActive = isCreatePage && activeService === svc.service;
          return (
            <Link
              key={svc.service}
              href={`/dashboard/create?service=${svc.service}`}
              className={cn(
                "flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-purple-500/20 text-white"
                  : "text-slate-300 hover:bg-white/10 hover:text-white",
              )}
            >
              <Icon className="h-4 w-4" />
              {svc.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
