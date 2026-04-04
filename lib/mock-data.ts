export type Project = {
  id: string;
  title: string;
  createdAt: string;
  thumbnail: string;
};

export const projects: Project[] = [
  {
    id: "launch-film",
    title: "Product Launch Film",
    createdAt: "Mar 28, 2026",
    thumbnail:
      "https://images.unsplash.com/photo-1579547621113-e4bb2a19bdd6?auto=format&fit=crop&w=1200&q=80",
  },
  {
    id: "app-ad",
    title: "App Promo Ad",
    createdAt: "Mar 24, 2026",
    thumbnail:
      "https://images.unsplash.com/photo-1470229538611-16ba8c7ffbd7?auto=format&fit=crop&w=1200&q=80",
  },
  {
    id: "fashion-story",
    title: "Fashion Story Teaser",
    createdAt: "Mar 20, 2026",
    thumbnail:
      "https://images.unsplash.com/photo-1557683316-973673baf926?auto=format&fit=crop&w=1200&q=80",
  },
  {
    id: "founder-message",
    title: "Founder Message",
    createdAt: "Mar 14, 2026",
    thumbnail:
      "https://images.unsplash.com/photo-1517180102446-f3ece451e9d8?auto=format&fit=crop&w=1200&q=80",
  },
];

export const pricingTiers = [
  {
    name: "Starter",
    price: "$19/mo",
    credits: "120 credits",
    description: "Best for testing short social clips.",
  },
  {
    name: "Pro",
    price: "$49/mo",
    credits: "500 credits",
    description: "Great for weekly campaign production.",
  },
  {
    name: "Scale",
    price: "$99/mo",
    credits: "1200 credits",
    description: "For teams shipping videos every day.",
  },
];

export type ServiceCapability = {
  name: string;
  category: "video" | "image" | "audio" | "avatar";
  description: string;
  highlights: string[];
};

export const serviceCapabilities: ServiceCapability[] = [
  {
    name: "Topic to Video",
    category: "video",
    description: "Turn a topic into script, scenes, and final video in one flow.",
    highlights: ["Auto script", "Scene storyboard", "Render-ready timeline"],
  },
  {
    name: "Image to Video",
    category: "video",
    description: "Animate still images into cinematic clips with smooth transitions.",
    highlights: ["Motion control", "Depth effects", "Style-consistent output"],
  },
  {
    name: "Text to Image",
    category: "image",
    description: "Generate high-quality visuals for every scene instantly.",
    highlights: ["Style presets", "Prompt enhancement", "Batch generations"],
  },
  {
    name: "Text to Voice",
    category: "audio",
    description: "Convert your script into natural, expressive AI voiceovers.",
    highlights: ["Multi-voice", "Emotion control", "Instant narration"],
  },
  {
    name: "Text to Music",
    category: "audio",
    description: "Create mood-based background tracks that match each scene.",
    highlights: ["Genre controls", "Loop generation", "Royalty-safe output"],
  },
  {
    name: "Avatar",
    category: "avatar",
    description: "Generate AI avatars for spokesperson, explainer, and social content.",
    highlights: ["Talking avatar", "Brand appearance", "Lip-sync support"],
  },
];
