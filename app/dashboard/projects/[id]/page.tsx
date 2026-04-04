import { notFound } from "next/navigation";
import { VideoEditor } from "@/components/dashboard/video-editor";
import { projects } from "@/lib/mock-data";

type ProjectEditorPageProps = {
  params: Promise<{
    id: string;
  }>;
};

export default async function ProjectEditorPage({ params }: ProjectEditorPageProps) {
  const { id } = await params;
  const project = projects.find((item) => item.id === id);

  if (!project) {
    notFound();
  }

  return <VideoEditor title={`Project: ${project.title}`} />;
}
