"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { mainLinks, serviceHref, serviceLinks } from "@/lib/dashboard-nav";

type SidebarContentProps = {
  onNavigate?: () => void;
  showBrand?: boolean;
};

/**
 * Reusable nav content — used inside the desktop `<aside>` rail and the
 * mobile hamburger drawer. `onNavigate` lets the drawer close itself when
 * a link is tapped.
 */
export function SidebarContent({ onNavigate, showBrand = true }: SidebarContentProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const activeService = searchParams.get("service") ?? "topic-to-video";
  const isCreatePage = pathname === "/dashboard/create";

  return (
    <div className="flex flex-col">
      {showBrand ? (
        <Link
          href="/"
          onClick={onNavigate}
          className="mb-8 flex items-center gap-2 text-lg font-semibold"
        >
          <Image
            src="/logo.png"
            alt="EnablyAI logo"
            width={24}
            height={24}
            className="rounded-md"
          />
          EnablyAI
        </Link>
      ) : null}

      <nav className="grid gap-1">
        {mainLinks.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              onClick={onNavigate}
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
              href={serviceHref(svc.service)}
              onClick={onNavigate}
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
    </div>
  );
}

/**
 * Desktop sidebar rail. Hidden below `md:` — the mobile experience uses the
 * hamburger drawer + bottom nav instead.
 */
export function DashboardSidebar() {
  return (
    <aside className="hidden border-r border-white/10 bg-[#0d1020] p-4 md:block md:w-64">
      <SidebarContent />
    </aside>
  );
}
