"use client";

import Link from "next/link";
import Image from "next/image";
import { useState } from "react";
import { ClayButton } from "@/components/clay-button";
import { Card } from "@/components/ui/card";
import { pricingTiers, serviceCapabilities } from "@/lib/mock-data";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import {
  AudioLines,
  Clapperboard,
  ImageIcon,
  Mic2,
  Music2,
  Sparkles,
  UserRound,
  WandSparkles,
  Workflow,
} from "lucide-react";

const fadeInUp = {
  initial: { opacity: 0, y: 24 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, amount: 0.25 },
  transition: { duration: 0.5, ease: "easeOut" as const },
};

export default function Home() {
  const ctaX = useMotionValue(0);
  const ctaY = useMotionValue(0);
  const springX = useSpring(ctaX, { stiffness: 180, damping: 18 });
  const springY = useSpring(ctaY, { stiffness: 180, damping: 18 });
  const rotateX = useTransform(springY, [-14, 14], [6, -6]);
  const rotateY = useTransform(springX, [-14, 14], [-6, 6]);
  const serviceIconMap = {
    "Topic to Video": Clapperboard,
    "Image to Video": WandSparkles,
    "Text to Image": ImageIcon,
    "Text to Voice": Mic2,
    "Text to Music": Music2,
    Avatar: UserRound,
  } as const;
  const [activeServiceTab, setActiveServiceTab] = useState<
    "all" | "video" | "image" | "audio" | "avatar"
  >("all");

  const filteredServices =
    activeServiceTab === "all"
      ? serviceCapabilities
      : serviceCapabilities.filter((service) => service.category === activeServiceTab);

  return (
    <div className="bg-aurora relative min-h-screen overflow-hidden">
      <div className="gradient-blob left-[-120px] top-[-80px] h-72 w-72 bg-purple-500/35" />
      <div className="gradient-blob bottom-[-60px] right-[-90px] h-80 w-80 bg-blue-500/30" />
      <main className="mx-auto max-w-6xl space-y-24 px-6 py-8 md:px-10 md:py-12">
        <nav className="glass flex items-center justify-between rounded-2xl px-5 py-3">
          <Link href="/" className="flex items-center gap-2 text-lg font-semibold">
            <Image
              src="/logo.png"
              alt="EnablyAI logo"
              width={28}
              height={28}
              className="rounded-md"
            />
            EnablyAI
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-slate-200 hover:text-white">
              Login
            </Link>
            <Link href="/signup" className="text-sm text-slate-200 hover:text-white">
              Signup
            </Link>
          </div>
        </nav>

        <motion.section {...fadeInUp} className="space-y-6 text-center md:space-y-8">
          <p className="inline-flex rounded-full border border-white/20 bg-white/10 px-4 py-1 text-sm text-slate-200">
            AI Video Generator Platform
          </p>
          <h1 className="mx-auto max-w-4xl text-4xl font-bold tracking-tight md:text-6xl">
            Create AI Videos in Seconds
          </h1>
          <p className="mx-auto max-w-2xl text-base text-slate-300 md:text-lg">
            Transform simple prompts into scenes, voiceovers, and export-ready videos
            with a simple workflow made for modern creators.
          </p>
          <div className="flex justify-center">
            <Link
              href="/signup"
              className="cta-glow float-subtle"
              onMouseMove={(event) => {
                const rect = event.currentTarget.getBoundingClientRect();
                const x = event.clientX - rect.left - rect.width / 2;
                const y = event.clientY - rect.top - rect.height / 2;
                ctaX.set(Math.max(-14, Math.min(14, x * 0.18)));
                ctaY.set(Math.max(-14, Math.min(14, y * 0.18)));
              }}
              onMouseLeave={() => {
                ctaX.set(0);
                ctaY.set(0);
              }}
            >
              <motion.div
                className="cta-magnetic"
                style={{ x: springX, y: springY, rotateX, rotateY, transformPerspective: 800 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.98 }}
              >
                <ClayButton className="px-8 py-3 text-base">Get Started</ClayButton>
              </motion.div>
            </Link>
          </div>
        </motion.section>

        <motion.section {...fadeInUp} className="grid gap-4 md:grid-cols-3">
          {["Text to Video", "Image to Video", "AI Voice"].map((feature) => (
            <motion.div
              key={feature}
              whileHover={{ y: -8, scale: 1.01 }}
              transition={{ duration: 0.25, ease: "easeOut" }}
            >
              <Card className="glass h-full transition hover:border-white/35 hover:bg-white/10">
                <p className="text-lg font-semibold">{feature}</p>
                <p className="mt-2 text-sm text-slate-300">
                  Fast generation pipeline with high-quality visuals and voice output.
                </p>
              </Card>
            </motion.div>
          ))}
        </motion.section>

        <motion.section {...fadeInUp} className="space-y-5">
          <div className="text-center">
            <h2 className="text-2xl font-semibold md:text-3xl">AI Services You Can Offer</h2>
            <p className="mt-2 text-sm text-slate-300">
              Topic to Video, Image to Video, Text to Image, Text to Voice, Text to
              Music, and Avatar generation in one premium workspace.
            </p>
          </div>
          <div className="mx-auto flex w-fit flex-wrap justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 p-1">
            {[
              { label: "All", value: "all" },
              { label: "Video", value: "video" },
              { label: "Image", value: "image" },
              { label: "Audio", value: "audio" },
              { label: "Avatar", value: "avatar" },
            ].map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() =>
                  setActiveServiceTab(
                    tab.value as "all" | "video" | "image" | "audio" | "avatar",
                  )
                }
                className={[
                  "rounded-xl px-3 py-1.5 text-xs font-medium transition",
                  activeServiceTab === tab.value
                    ? "bg-purple-400/25 text-white shadow-[0_0_22px_rgba(142,119,255,0.35)]"
                    : "text-slate-300 hover:bg-white/10 hover:text-white",
                ].join(" ")}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredServices.map((service) => {
              const Icon = serviceIconMap[service.name as keyof typeof serviceIconMap] ?? Sparkles;
              return (
                <motion.div
                  key={service.name}
                  whileHover={{ y: -6 }}
                  transition={{ duration: 0.22, ease: "easeOut" }}
                >
                  <Card className="glass overflow-hidden p-0">
                    <div className="relative border-b border-white/10 bg-gradient-to-br from-purple-500/20 via-blue-500/10 to-white/5 px-4 py-4">
                      <div className="mb-3 flex items-center justify-between">
                        <span className="rounded-full border border-white/20 bg-white/5 p-2">
                          <Icon className="h-4 w-4 text-purple-100" />
                        </span>
                        <span className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-slate-300">
                          AI Core
                        </span>
                      </div>
                      <div className="space-y-2">
                        <div className="h-1.5 rounded-full bg-white/10">
                          <div className="h-1.5 w-[82%] rounded-full bg-gradient-to-r from-purple-300 to-blue-300" />
                        </div>
                        <div className="h-1.5 rounded-full bg-white/10">
                          <div className="h-1.5 w-[64%] rounded-full bg-gradient-to-r from-blue-300 to-cyan-300" />
                        </div>
                        <div className="h-1.5 rounded-full bg-white/10">
                          <div className="h-1.5 w-[72%] rounded-full bg-gradient-to-r from-indigo-300 to-purple-300" />
                        </div>
                      </div>
                    </div>
                    <div className="p-4">
                      <p className="text-base font-semibold">{service.name}</p>
                      <p className="mt-2 text-sm text-slate-300">{service.description}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {service.highlights.map((item) => (
                          <span
                            key={item}
                            className="rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-slate-200"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </div>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </motion.section>

        <motion.section {...fadeInUp} className="glass rounded-3xl p-6 md:p-8">
          <h2 className="text-2xl font-semibold">Demo Workflow</h2>
          <p className="mt-2 text-sm text-slate-300">
            Prompt → Scene generation → Voice sync → Preview → Export
          </p>
          <div className="mt-5 grid gap-3 md:grid-cols-4">
            {[
              { step: "Prompt", icon: Sparkles, hint: "Describe your idea" },
              { step: "Scenes", icon: WandSparkles, hint: "Generate keyframes" },
              { step: "Voice", icon: AudioLines, hint: "Sync narration" },
              { step: "Export", icon: Workflow, hint: "Publish instantly" },
            ].map(({ step, icon: Icon, hint }, index) => (
              <motion.div
                key={step}
                whileHover={{ y: -5 }}
                className="group rounded-2xl border border-white/20 bg-white/5 px-4 py-5"
              >
                <div className="mb-3 flex items-center justify-between">
                  <span className="rounded-full border border-white/20 px-2 py-0.5 text-xs text-slate-300">
                    0{index + 1}
                  </span>
                  <Icon className="h-4 w-4 text-purple-200 group-hover:text-white" />
                </div>
                <p className="text-sm font-medium text-slate-100">{step}</p>
                <div className="mt-2 h-1 w-full rounded-full bg-white/10">
                  <div className="h-1 w-2/3 rounded-full bg-gradient-to-r from-purple-300 to-blue-300" />
                </div>
                <p className="mt-2 text-xs text-slate-300">{hint}</p>
              </motion.div>
            ))}
          </div>
        </motion.section>

        <motion.section {...fadeInUp} className="space-y-6">
          <h2 className="text-center text-2xl font-semibold md:text-3xl">Pricing</h2>
          <p className="text-center text-sm text-slate-300">
            Credits are consumed based on feature, quality, and duration. Sign in to see your live balance.
          </p>
          <div className="grid items-stretch gap-5 md:grid-cols-3">
            {pricingTiers.map((tier) => (
              <motion.div
                key={tier.name}
                whileHover={{ y: -8 }}
                className={tier.featured ? "relative scale-[1.02]" : ""}
              >
                {tier.featured ? (
                  <div className="pointer-events-none absolute inset-[-10px] -z-10 rounded-3xl bg-gradient-to-r from-purple-500/35 to-blue-500/35 blur-xl" />
                ) : null}
                <Card
                  className={[
                    "glass h-full transition",
                    tier.featured
                      ? "pro-spotlight border-purple-300/55 shadow-[0_22px_55px_rgba(112,92,255,0.35)]"
                      : "hover:border-purple-300/40 hover:shadow-[0_20px_45px_rgba(76,58,164,0.35)]",
                  ].join(" ")}
                >
                  {tier.badge ? (
                    <span className="mb-3 inline-flex rounded-full border border-purple-300/40 bg-purple-300/15 px-3 py-1 text-xs font-medium text-purple-100">
                      {tier.badge}
                    </span>
                  ) : null}
                  <p className="text-lg font-semibold">{tier.name}</p>
                  <p className="mt-3 text-2xl font-bold md:text-3xl">{tier.price}</p>
                  <p className="mt-2 text-sm text-orange-200">{tier.credits}</p>
                  <p className="mt-4 text-sm leading-relaxed text-slate-300">{tier.description}</p>
                </Card>
              </motion.div>
            ))}
          </div>
        </motion.section>

        <footer className="border-t border-white/10 py-8 text-center text-sm text-slate-300">
          EnablyAI 2026. Build videos with AI, faster.
        </footer>
      </main>
    </div>
  );
}
