"use client";

import { useEffect, useState } from "react";
import { useGame } from "@/context/GameContext";
import { useCampaignHistory } from "@/hooks/useCampaignHistory";
import { GAME_CATALOG } from "@/lib/games";
import { ConsoleProvider } from "./ConsoleProvider";
import { LayoutSwitcher } from "./LayoutSwitcher";
import { DEFAULT_LAYOUT_ID, getLayout } from "./layouts";

const LAYOUT_STORAGE_KEY = "dnd.console.layout";

/**
 * Mounts the interactive console: reads the active campaign id (minted at
 * "Confirm & Begin" for new games, or the saved id for resume), loads its
 * history, and renders the chosen layout around the shared provider.
 */
export function ConsoleHost() {
  const { state: game } = useGame();

  // The session id is shared via GameContext so it matches the id the first turn
  // was submitted under (see BEGIN_NEW_CAMPAIGN / SELECT_CAMPAIGN).
  const campaignId = game.campaignId;

  const { history, progress, summary, loading, reload } = useCampaignHistory(campaignId);

  // Layout choice, persisted. Start from the default so SSR and first client
  // render match; hydrate the stored choice in an effect.
  const [layoutId, setLayoutId] = useState<string>(DEFAULT_LAYOUT_ID);
  useEffect(() => {
    const stored = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (stored) setLayoutId(stored);
  }, []);
  useEffect(() => {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, layoutId);
  }, [layoutId]);

  const ActiveLayout = getLayout(layoutId).Component;

  const title =
    GAME_CATALOG.find((g) => g.id === game.selectedGameId)?.title ??
    (game.branch === "resume" ? "Resumed campaign" : "New campaign");

  return (
    <div className="h-screen w-full px-3 pb-3 pt-14 sm:px-5 sm:pt-16">
      <ConsoleProvider
        campaignId={campaignId}
        history={history}
        historyLoading={loading}
        progress={progress}
        summary={summary}
        reloadHistory={reload}
      >
        <div className="flex h-full flex-col gap-3">
          <header className="flex shrink-0 items-center justify-between gap-3">
            <h1 className="text-gilded font-display text-lg font-bold tracking-wide sm:text-xl">
              {title}
            </h1>
            <LayoutSwitcher value={layoutId} onChange={setLayoutId} />
          </header>
          <div className="min-h-0 flex-1">
            <ActiveLayout />
          </div>
        </div>
      </ConsoleProvider>
    </div>
  );
}
