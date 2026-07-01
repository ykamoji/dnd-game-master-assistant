"use client";

import { Card } from "@/components/ui/Card";
import { Loader } from "@/components/ui/Loader";
import { SectionShell } from "@/components/ui/SectionShell";
import { useGame } from "@/context/GameContext";
import { useCampaigns } from "@/hooks/useCampaigns";
import { GAME_CATALOG } from "@/lib/games";

// Fallback cover when a saved campaign has no asset art yet.
const coverFor = (campaignName?: string, coverUrl?: string | null) => {
  if (coverUrl) return coverUrl;
  const match = GAME_CATALOG.find(
    (g) => g.title.toLowerCase() === (campaignName ?? "").toLowerCase(),
  );
  return match?.coverUrl ?? "/placeholders/still-1.svg";
};

/** Resume branch: list saved campaigns; selecting one dissolves to the console. */
export function ResumeView() {
  const { dispatch } = useGame();
  const { campaigns, loading, error } = useCampaigns();

  const select = (id: string) => {
    dispatch({ type: "SELECT_CAMPAIGN", campaignId: id });
    dispatch({ type: "START_DISSOLVE" });
  };

  return (
    <SectionShell>
      {/* Header section */}
      <div className="mb-12 flex flex-col items-center text-center px-6">
        <h2 className="text-gilded font-display text-4xl font-bold tracking-wide sm:text-5xl">
          Resume a Saga
        </h2>
        <p className="mt-3 font-rune text-parchment-dim">
          Choose a saved campaign to continue where the story paused.
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Loader label="Recalling your tales…" />
        </div>
      )}
      {error && (
        <p className="text-center text-blood-bright px-6">
          Could not load campaigns: {error}
        </p>
      )}
      {!loading && !error && campaigns.length === 0 && (
        <p className="text-center font-rune text-parchment-dim px-6">
          No saved campaigns yet — start a new one to begin your legend.
        </p>
      )}

      {/* Cinematic Horizontal Scroll */}
      {!loading && !error && campaigns.length > 0 && (
        <div className="flex w-[calc(100%+3rem)] -mx-6 snap-x snap-mandatory gap-6 overflow-x-auto px-[max(10vw,1.5rem)] pb-12 pt-10 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
          {campaigns.map((c) => (
            <div
              key={c.campaign_id}
              className="w-[300px] shrink-0 snap-center sm:w-[350px] transition-transform duration-300 hover:-translate-y-2 hover:scale-[1.02]"
            >
              <Card
                title={c.campaign_name || c.campaign_id}
                description={c.summary || c.scene || "An adventure in progress."}
                imageUrl={coverFor(c.campaign_name, c.cover_url)}
                badge={
                  typeof c.progress === "number"
                    ? `${Math.round(c.progress)}%`
                    : undefined
                }
                onClick={() => select(c.campaign_id)}
              />
            </div>
          ))}
          {/* Spacer to ensure the last card can scroll to the center */}
          <div className="w-[10vw] shrink-0" aria-hidden />
        </div>
      )}
    </SectionShell>
  );
}
