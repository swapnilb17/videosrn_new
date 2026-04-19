"use client";

import Link from "next/link";
import { Card } from "@/components/ui/card";
import { projects } from "@/lib/mock-data";
import { ProjectCard } from "@/components/dashboard/project-card";
import { STARTER_BUNDLE_CREDIT_CAP } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function DashboardPage() {
  const { creditsInfo, creditsError, creditsLoading } = useAuth();

  const showPayStarter =
    !creditsError &&
    !creditsLoading &&
    creditsInfo?.creditsEnabled === true &&
    (creditsInfo?.balance ?? 0) < STARTER_BUNDLE_CREDIT_CAP;

  const planLabel = creditsInfo?.plan === "starter" ? "Starter" : "Free";
  const balanceLine =
    creditsInfo != null ? `${creditsInfo.balance} credits` : "…";
  const planDescription =
    creditsInfo?.plan === "starter"
      ? "Premium Veo video is enabled. Usage bills credits per second of output."
      : "Signup credits included. Redeem a code in Settings to unlock Starter (Veo + premium).";

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <Card className="glass space-y-2">
          <h1 className="text-2xl font-semibold">Welcome back</h1>
          <p className="text-sm text-slate-300">
            Keep your workflow simple: write prompt, generate, preview, export.
          </p>
          <Link
            href="/dashboard/create"
            className="inline-flex rounded-xl bg-purple-500/25 px-4 py-2 text-sm font-medium text-purple-100 hover:bg-purple-500/35"
          >
            Start new video
          </Link>
        </Card>
        <Card className="space-y-2">
          <p className="text-sm text-slate-300">Your plan</p>
          <p className="text-xl font-semibold">
            {creditsInfo != null ? planLabel : "…"}
          </p>
          <p className="text-sm text-orange-200">{balanceLine}</p>
          <p className="text-sm text-slate-300">
            {creditsInfo != null ? planDescription : "Loading…"}
          </p>
          {creditsInfo?.plan === "free" && creditsInfo.starterRedeemAvailable ? (
            <Link
              href="/dashboard/settings"
              className="inline-block text-sm text-purple-300 hover:text-purple-200 hover:underline"
            >
              Redeem Starter code
            </Link>
          ) : null}
          {showPayStarter ? (
            <Link
              href="/dashboard/settings#pay-starter"
              className="inline-block text-sm text-emerald-300/90 hover:text-emerald-200 hover:underline"
            >
              Pay ₹499 for Starter (Razorpay)
            </Link>
          ) : null}
        </Card>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent projects</h2>
          <Link href="/dashboard/projects" className="text-sm text-slate-300 hover:text-white">
            View all
          </Link>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.slice(0, 3).map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      </section>
    </div>
  );
}
