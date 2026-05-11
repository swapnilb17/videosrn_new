import {
  Clapperboard,
  Film,
  FolderKanban,
  GalleryHorizontalEnd,
  Home,
  ImageIcon,
  type LucideIcon,
  Megaphone,
  Mic,
  Settings,
  Sparkles,
} from "lucide-react";

export type MainNavLink = {
  href: string;
  label: string;
  icon: LucideIcon;
};

export type ServiceNavLink = {
  service: string;
  label: string;
  description: string;
  icon: LucideIcon;
  badge?: string;
};

export const mainLinks: MainNavLink[] = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/dashboard/templates", label: "Templates", icon: Sparkles },
  { href: "/dashboard/media", label: "Media Library", icon: GalleryHorizontalEnd },
  { href: "/dashboard/projects", label: "Projects", icon: FolderKanban },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export const serviceLinks: ServiceNavLink[] = [
  {
    service: "topic-to-video",
    label: "Topic to Video",
    description: "Turn an idea into a finished clip",
    icon: Film,
    badge: "Most popular",
  },
  {
    service: "text-to-image",
    label: "Text to Image",
    description: "Generate visuals from a prompt",
    icon: ImageIcon,
  },
  {
    service: "text-to-voice",
    label: "Text to Voice",
    description: "Synthesize natural speech",
    icon: Mic,
  },
  {
    service: "photo-to-video",
    label: "Image to Video",
    description: "Animate a still photo",
    icon: Clapperboard,
  },
  {
    service: "image-to-ad",
    label: "Image to AD Video",
    description: "Create ad creatives in seconds",
    icon: Megaphone,
  },
];

export function serviceHref(service: string): string {
  return `/dashboard/create?service=${service}`;
}
