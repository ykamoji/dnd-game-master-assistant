"use client";

import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { SectionShell } from "@/components/ui/SectionShell";
import { useGame } from "@/context/GameContext";
import { GAME_CATALOG } from "@/lib/games";

/** New-campaign step 1: pick an adventure. Only ToA is playable. */
export function CampaignSelectView() {
  const { dispatch } = useGame();
  const [comingSoon, setComingSoon] = useState<string | null>(null);

  return (
    <SectionShell>
      <div className="mb-12 flex flex-col items-center text-center px-6">
        <h2 className="text-gilded font-display text-4xl font-bold tracking-wide sm:text-5xl">
          Choose Your Adventure
        </h2>
        <p className="mt-3 font-rune text-parchment-dim">
          Select a published campaign to embark upon.
        </p>
      </div>

      <div className="flex w-[calc(100%+3rem)] -mx-6 snap-x snap-mandatory gap-6 overflow-x-auto px-[max(20vw,1.5rem)] pb-12 pt-10 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
        {GAME_CATALOG.map((game) => (
          <div
            key={game.id}
            className="w-[300px] shrink-0 snap-center sm:w-[350px] transition-transform duration-300 hover:-translate-y-2 hover:scale-[1.02]"
          >
            <Card
              title={game.title}
              description={game.blurb}
              imageUrl={game.coverUrl}
              badge={game.available ? undefined : "Coming Soon"}
              disabled={!game.available}
              onClick={() =>
                game.available
                  ? dispatch({ type: "SELECT_GAME", gameId: game.id })
                  : setComingSoon(game.title)
              }
            />
          </div>
        ))}
        {/* Spacer to ensure the last card can scroll to the center */}
        <div className="w-[10vw] shrink-0" aria-hidden />
      </div>

      <Modal
        open={comingSoon !== null}
        title="Not Yet Unsealed"
        size="xs"
        onClose={() => setComingSoon(null)}
      >
        <p>
          <span className="text-gold-bright">{comingSoon}</span> is still being
          prepared by the Game Master. For now, only{" "}
          <span className="text-gold-bright">Tomb of Annihilation</span> is ready
          to play.
        </p>
      </Modal>
    </SectionShell>
  );
}
