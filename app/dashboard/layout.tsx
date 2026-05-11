"use client";

import { Suspense } from "react";
import { DashboardSidebar } from "@/components/dashboard/sidebar";
import { DashboardTopbar } from "@/components/dashboard/topbar";
import { MobileTopbar } from "@/components/dashboard/mobile-topbar";
import { MobileNav } from "@/components/dashboard/mobile-nav";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="bg-aurora flex min-h-screen items-center justify-center text-sm text-slate-200">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-purple-400 border-t-transparent" />
          Loading...
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="bg-aurora flex min-h-screen items-center justify-center text-sm text-slate-200">
        Redirecting...
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Suspense>
        <DashboardSidebar />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col">
        <MobileTopbar />
        <DashboardTopbar />
        <main className="flex-1 bg-[#0a0d1b] p-4 pb-[calc(5.5rem+env(safe-area-inset-bottom))] md:p-6 md:pb-6">
          {children}
        </main>
      </div>
      <MobileNav />
    </div>
  );
}
