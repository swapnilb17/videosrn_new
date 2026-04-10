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

/** Public marketing copy — aligns with in-app Free vs Starter (redeem) billing. */
export type PricingTier = {
  name: string;
  price: string;
  credits: string;
  description: string;
  /** Gradient + “hero” card styling */
  featured?: boolean;
  badge?: string;
};

export const pricingTiers: PricingTier[] = [
  {
    name: "Free",
    price: "$0",
    credits: "50 credits on signup",
    description:
      "Core generation: images, voice, and standard video. Each action debits credits from your balance.",
  },
  {
    name: "Starter",
    price: "Redeem in Settings",
    credits: "Up to 500 credits on redeem",
    description:
      "Unlock premium Veo (image/video) with a redeem code; balance is topped up to 500 credits if below. Premium usage still bills per second.",
    featured: true,
    badge: "Unlock premium",
  },
  {
    name: "Teams",
    price: "Contact us",
    credits: "Custom volume",
    description: "Higher limits, shared workspaces, and invoicing for agencies. Reach out when you’re ready to scale.",
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
