"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import {
  ChevronRight,
  FolderKanban,
  GalleryHorizontalEnd,
  Home,
  LogOut,
  type LucideIcon,
  MoreHorizontal,
  Plus,
  Settings,
  Sparkles,
} from "lucide-react";
import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { serviceHref, serviceLinks } from "@/lib/dashboard-nav";
import { useAuth } from "@/lib/auth-context";

type FlatItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  match: (pathname: string) => boolean;
};

const flatItems: FlatItem[] = [
  {
    href: "/dashboard",
    label: "Home",
    icon: Home,
    match: (p) => p === "/dashboard",
  },
  {
    href: "/dashboard/templates",
    label: "Templates",
    icon: Sparkles,
    match: (p) => p.startsWith("/dashboard/templates"),
  },
  {
    href: "/dashboard/media",
    label: "Media",
    icon: GalleryHorizontalEnd,
    match: (p) => p.startsWith("/dashboard/media"),
  },
];

function MobileNavInner() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { logout } = useAuth();
  const [createOpen, setCreateOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  const isCreateActive = pathname.startsWith("/dashboard/create");
  const activeService = searchParams.get("service") ?? "topic-to-video";

  function pickService(service: string) {
    setCreateOpen(false);
    router.push(serviceHref(service));
  }

  return (
    <>
      <nav
        aria-label="Primary"
        className={cn(
          "fixed bottom-0 left-0 right-0 z-40 md:hidden",
          "border-t border-white/10 bg-[#0b0f1f]/95 backdrop-blur-xl",
          "pb-[max(0.25rem,env(safe-area-inset-bottom))]",
        )}
      >
        <ul className="relative mx-auto flex max-w-md items-stretch justify-between px-2 pt-1">
          {flatItems.slice(0, 2).map((item) => (
            <FlatNavLink key={item.href} item={item} active={item.match(pathname)} />
          ))}

          <li className="relative flex flex-1 flex-col items-center justify-end gap-1 py-2 text-[11px]">
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              aria-label="Create"
              aria-expanded={createOpen}
              className={cn(
                "clay absolute bottom-7 left-1/2 flex h-12 w-12 -translate-x-1/2 items-center justify-center rounded-2xl text-white",
                "shadow-[0_10px_30px_rgba(112,92,255,0.55)]",
                isCreateActive
                  ? "ring-2 ring-purple-300/70 ring-offset-2 ring-offset-[#0b0f1f]"
                  : "",
              )}
            >
              <Plus className="h-6 w-6" strokeWidth={2.5} />
            </button>
            <span aria-hidden="true" className="block h-5 w-5" />
            <span
              className={cn(
                "pointer-events-none font-medium",
                isCreateActive ? "text-white" : "text-slate-400",
              )}
            >
              Create
            </span>
          </li>

          {flatItems.slice(2).map((item) => (
            <FlatNavLink key={item.href} item={item} active={item.match(pathname)} />
          ))}

          <MoreNavButton onOpen={() => setMoreOpen(true)} />
        </ul>
      </nav>

      <Sheet
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        side="bottom"
        title="Create"
        description="Choose what to make"
      >
        <ul className="space-y-2 pt-1">
          {serviceLinks.map((svc) => {
            const Icon = svc.icon;
            const isActive = isCreateActive && activeService === svc.service;
            return (
              <li key={svc.service}>
                <button
                  type="button"
                  onClick={() => pickService(svc.service)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-2xl border px-3 py-3 text-left transition active:scale-[0.99]",
                    isActive
                      ? "border-purple-400/50 bg-purple-500/15"
                      : "border-white/10 bg-white/5",
                  )}
                >
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-purple-500 to-blue-500 text-white shadow-[0_8px_20px_rgba(112,92,255,0.35)]">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold text-white">
                        {svc.label}
                      </span>
                      {svc.badge ? (
                        <span className="rounded-full border border-purple-300/40 bg-purple-300/15 px-2 py-0.5 text-[10px] font-medium text-purple-100">
                          {svc.badge}
                        </span>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-slate-400">
                      {svc.description}
                    </span>
                  </span>
                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
                </button>
              </li>
            );
          })}
        </ul>
      </Sheet>

      <Sheet
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        side="bottom"
        title="More"
      >
        <div className="space-y-2 pt-1">
          <Link
            href="/dashboard/projects"
            onClick={() => setMoreOpen(false)}
            className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-200 transition active:bg-white/10"
          >
            <FolderKanban className="h-4 w-4 text-slate-300" />
            Projects
          </Link>
          <Link
            href="/dashboard/settings"
            onClick={() => setMoreOpen(false)}
            className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-slate-200 transition active:bg-white/10"
          >
            <Settings className="h-4 w-4 text-slate-300" />
            Settings &amp; billing
          </Link>
          <button
            type="button"
            onClick={() => {
              setMoreOpen(false);
              logout();
            }}
            className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-rose-200 transition active:bg-white/10"
          >
            <LogOut className="h-4 w-4" />
            Log out
          </button>
        </div>
      </Sheet>
    </>
  );
}

function FlatNavLink({ item, active }: { item: FlatItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <li className="flex flex-1">
      <Link
        href={item.href}
        className={cn(
          "flex flex-1 flex-col items-center justify-end gap-1 py-2 text-[11px] transition",
          active ? "text-white" : "text-slate-400 active:text-white",
        )}
      >
        <Icon
          className={cn(
            "h-5 w-5",
            active ? "text-white drop-shadow-[0_0_10px_rgba(166,135,255,0.7)]" : "",
          )}
        />
        <span className="font-medium">{item.label}</span>
      </Link>
    </li>
  );
}

function MoreNavButton({ onOpen }: { onOpen: () => void }) {
  return (
    <li className="flex flex-1">
      <button
        type="button"
        onClick={onOpen}
        aria-label="More options"
        className="flex flex-1 flex-col items-center justify-end gap-1 py-2 text-[11px] text-slate-400 transition active:text-white"
      >
        <MoreHorizontal className="h-5 w-5" />
        <span className="font-medium">More</span>
      </button>
    </li>
  );
}

export function MobileNav() {
  return (
    <Suspense fallback={null}>
      <MobileNavInner />
    </Suspense>
  );
}
