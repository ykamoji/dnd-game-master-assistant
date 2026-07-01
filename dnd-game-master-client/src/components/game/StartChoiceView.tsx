"use client";

import { motion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { SectionShell } from "@/components/ui/SectionShell";
import { useGame } from "@/context/GameContext";

/** First view: choose to start a new campaign or resume a saved one. */
export function StartChoiceView() {
  const { dispatch } = useGame();

  return (
    <SectionShell className="bg-obsidian">
      <div className="flex flex-col items-center text-center">
        <motion.h2
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-gilded font-display text-4xl font-bold tracking-wide sm:text-5xl"
        >
          Begin Your Saga
        </motion.h2>
        <p className="mt-4 max-w-xl font-rune text-lg text-parchment-dim">
          Will you forge a new legend, or return to a tale already in motion?
        </p>

        <div className="mt-12 flex flex-col gap-4 sm:flex-row">
          <Button
            size="lg"
            onClick={() => dispatch({ type: "CHOOSE_BRANCH", branch: "new" })}
          >
            New Campaign
          </Button>
          <div className="flex items-cente p-5">
            OR
          </div>
          <Button
            size="lg"
            variant="secondary"
            onClick={() => dispatch({ type: "CHOOSE_BRANCH", branch: "resume" })}
          >
            Resume Campaign
          </Button>
        </div>
      </div>
    </SectionShell>
  );
}
