"use client";

import { Suspense } from "react";
import { DashboardSidebar } from "@/components/dashboard/sidebar";
import { DashboardTopbar } from "@/components/dashboard/topbar";
import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function DashboardLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const { isAuthenticated } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, router]);

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
        <DashboardTopbar />
        <main className="flex-1 bg-[#0a0d1b] p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
