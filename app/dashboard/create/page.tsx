"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { VideoEditor } from "@/components/dashboard/video-editor";
import { TextToImage } from "@/components/dashboard/text-to-image";
import { TextToVoice } from "@/components/dashboard/text-to-voice";
import { PhotoToVideo } from "@/components/dashboard/photo-to-video";
import { ImageToAdVideo } from "@/components/dashboard/image-to-ad-video";

function CreateContent() {
  const searchParams = useSearchParams();
  const service = searchParams.get("service") ?? "topic-to-video";

  return (
    <>
      {service === "topic-to-video" && <VideoEditor title="Topic to Video" />}
      {service === "text-to-image" && <TextToImage />}
      {service === "text-to-voice" && <TextToVoice />}
      {service === "photo-to-video" && <PhotoToVideo />}
      {service === "image-to-ad" && <ImageToAdVideo />}
    </>
  );
}

export default function CreatePage() {
  return (
    <Suspense>
      <CreateContent />
    </Suspense>
  );
}
