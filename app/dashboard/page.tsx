import Link from "next/link";
import { Card } from "@/components/ui/card";
import { projects, pricingTiers } from "@/lib/mock-data";
import { ProjectCard } from "@/components/dashboard/project-card";

export default function DashboardPage() {
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
          <p className="text-sm text-slate-300">Suggested plan</p>
          <p className="text-xl font-semibold">{pricingTiers[1].name}</p>
          <p className="text-sm text-orange-200">{pricingTiers[1].credits}</p>
          <p className="text-sm text-slate-300">{pricingTiers[1].description}</p>
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
