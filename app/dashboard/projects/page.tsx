import { ProjectCard } from "@/components/dashboard/project-card";
import { projects } from "@/lib/mock-data";

export default function ProjectsPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Projects</h1>
      <p className="text-sm text-slate-300">
        Open any project to continue editing and exporting.
      </p>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {projects.map((project) => (
          <ProjectCard key={project.id} project={project} />
        ))}
      </div>
    </div>
  );
}
