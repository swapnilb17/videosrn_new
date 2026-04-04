import Image from "next/image";
import Link from "next/link";
import type { Project } from "@/lib/mock-data";

export function ProjectCard({ project }: { project: Project }) {
  return (
    <Link
      href={`/dashboard/projects/${project.id}`}
      className="group overflow-hidden rounded-2xl border border-white/15 bg-white/5 transition hover:-translate-y-1 hover:bg-white/10"
    >
      <div className="relative h-40 w-full">
        <Image
          src={project.thumbnail}
          alt={project.title}
          fill
          className="object-cover transition duration-500 group-hover:scale-105"
        />
      </div>
      <div className="p-4">
        <p className="text-base font-semibold">{project.title}</p>
        <p className="mt-1 text-sm text-slate-300">{project.createdAt}</p>
      </div>
    </Link>
  );
}
