"use client";

import { Hero } from "@/components/landing/Hero";
import { HowToPlay } from "@/components/landing/HowToPlay";
import { StillsCarousel } from "@/components/landing/StillsCarousel";

export function LandingView() {
  return (
    <div className="w-full">
      {/* View 1 — hero over the rotating slideshow background; scroll to continue */}
      <section className="relative flex min-h-screen items-center justify-center overflow-hidden">
        <StillsCarousel />
        <div className="absolute inset-0 bg-gradient-to-b from-obsidian/75 via-obsidian/55 to-obsidian" />
        <div className="relative z-10 w-full max-w-3xl px-6">
          <Hero />
        </div>
      </section>

      {/* View 2 — how to play + the call to enter the game */}
      <section id="how-to-play" className="flex min-h-screen flex-col items-center justify-center px-6 py-20 bg-obsidian-2">
        <div className="w-full max-w-6xl">
          <HowToPlay />
        </div>
      </section>
    </div>
  );
}
