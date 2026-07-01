"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/Button";
import { useGame } from "@/context/GameContext";

const STEPS = [
  {
    n: "I",
    title: "Choose your adventure",
    body: "Select a published campaign. Tomb of Annihilation awaits in the jungles of Chult; more are on the way.",
  },
  {
    n: "II",
    title: "Gather your party",
    body: "Start a new campaign and forge up to six heroes — pick a class and an archetype role for each, or summon the recommended party.",
  },
  {
    n: "III",
    title: "Speak and act",
    body: "Describe what your heroes do. The Game Master narrates outcomes, rolls the dice, and voices the world around you.",
  },
  {
    n: "IV",
    title: "Your saga persists",
    body: "Every scene is remembered. Leave and resume a saved campaign exactly where the story paused.",
  },
];

/** "How to play" view — explains how to use the app and starts the game. */
export function HowToPlay() {
  const { dispatch, state } = useGame();

  const startTransition = () => {
    if (state.dissolving) return;
    sessionStorage.removeItem("dnd-game-state");
    sessionStorage.removeItem("dnd-game-assemble-start");
    dispatch({ type: "START_NEW_SESSION" });
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Enter") {
        startTransition();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [state.dissolving, dispatch]);

  return (
    <>
      <div className="w-full bg-obsidian rounded-3xl">
        <h2 className="text-gilded mb-8 text-center font-display text-3xl font-bold tracking-wide sm:text-4xl">
          How to Play
        </h2>
        <div className="grid gap-5 sm:grid-cols-2">
          {STEPS.map((s) => (
            <div
              key={s.n}
              className="parchment flex gap-4 rounded-card border border-gold/20 p-5"
            >
              <span className="text-gilded font-display text-3xl font-black leading-none">
                {s.n}
              </span>
              <div>
                <h3 className="font-display text-lg font-semibold tracking-wide text-parchment">
                  {s.title}
                </h3>
                <p className="mt-1 text-md leading-relaxed text-parchment-dim">
                  {s.body}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-12 flex justify-center">
          <Button size="lg" onClick={startTransition}>
            Enter the Table
          </Button>
        </div>
      </div>
    </>
  );
}
