import { TemplatesGallery } from "@/components/dashboard/templates-gallery";

export const metadata = { title: "Templates · EnablyAI" };

export default function TemplatesPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Templates</h1>
        <p className="mt-1 text-sm text-slate-300">
          Trending creatives curated for you. Click a template to start a new
          project with it.
        </p>
      </div>
      <TemplatesGallery />
    </div>
  );
}
