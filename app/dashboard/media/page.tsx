import { MediaGallery } from "@/components/dashboard/media-gallery";

export default function MediaLibraryPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Media Library</h1>
        <p className="mt-1 text-sm text-slate-300">
          All your generated videos, images, and voice-overs in one place.
        </p>
      </div>
      <MediaGallery />
    </div>
  );
}
