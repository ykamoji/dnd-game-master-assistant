"use client";

import { type ReactNode, useState } from "react";
import { Loader } from "@/components/ui/Loader";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { useConsole } from "../ConsoleProvider";
import { intentMeta } from "../snapshot";
import { AssetGallery } from "../parts/AssetGallery";
import { PartyStatGrid } from "../parts/PartyStatGrid";
import { EventTimeline } from "../parts/EventTimeline";
import { ApprovalBar } from "../parts/ApprovalBar";
import type { CombatEntry, DialogueLine, SessionEvent, TurnSnapshot, PartyState } from "@/lib/types";

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="mb-2 font-display text-[10px] uppercase tracking-[0.3em] text-gold">
      {children}
    </p>
  );
}

function DialogueBlock({ lines }: { lines: DialogueLine[] }) {
  return (
    <div className="space-y-2">
      {lines.map((d, i) => (
        <p key={i} className="font-body text-parchment">
          <span className="font-display text-sm text-gold-bright">{d.speaker}</span>
          {d.emotion && (
            <span className="font-rune text-xs text-parchment-dim"> ({d.emotion})</span>
          )}
          <span className="text-parchment-dim">: </span>
          <span className="italic">“{d.text}”</span>
        </p>
      ))}
    </div>
  );
}

function CombatTable({ log }: { log: CombatEntry[] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="text-left font-display text-[10px] uppercase tracking-widest text-gold">
          <th className="py-1 pr-2">Action</th>
          <th className="py-1 pr-2">Target</th>
          <th className="py-1 pr-2">Roll</th>
          <th className="py-1">Result</th>
        </tr>
      </thead>
      <tbody>
        {log.map((e, i) => (
          <tr key={i} className="border-t border-stone-2 text-parchment">
            <td className="py-1 pr-2">{e.action}</td>
            <td className="py-1 pr-2 text-parchment-dim">{e.target}</td>
            <td className="py-1 pr-2 text-parchment-dim">{e.roll}</td>
            <td className="py-1">{e.result}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SuggestionChips({
  title,
  items,
  onPick,
}: {
  title: string;
  items: string[];
  onPick: (text: string) => void;
}) {
  if (!items?.length) return null;
  return (
    <div>
      <SectionLabel>{title}</SectionLabel>
      <div className="flex flex-wrap gap-2">
        {items.map((s, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onPick(s)}
            className="rounded-full cursor-pointer border border-gold/30 bg-obsidian-2 px-3 py-1 text-left text-sm text-parchment transition-colors hover:border-gold hover:text-gold-bright"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function parseDraftToSnapshot(draft: string): TurnSnapshot | null {
  try {
    const match = draft.match(/\{[\s\S]*\}/);
    if (!match) return null;
    const data = JSON.parse(match[0]);

    let partyState: PartyState | undefined;
    if (Array.isArray(data.party)) {
      partyState = { characters: {} };
      for (const char of data.party) {
        if (char.name) {
          partyState.characters[char.name] = char;
        }
      }
    }

    return {
      scene: data.scene_summary,
      description: data.description,
      narrative: data.narrative,
      dialogue: data.dialogue,
      initiative: data.initiative,
      party: partyState,
      intent: data.intent || "CAMPAIGN",
      metadata: {
        chapter: data.chapter,
        section: data.section,
        assets: data.assets,
        gm_notes: data.gm_notes,
        next_scene_suggestions: data.next_scene_suggestions,
        suggested_actions: data.suggested_actions,
        combat_log: data.combat_log,
        math_breakdown: data.math_breakdown,
        requires_roll: data.requires_roll
      }
    };
  } catch (e) {
    return null;
  }
}

function SnapshotLayout({
  snapshot,
  progress,
  summary,
  setComposerDraft,
}: {
  snapshot: TurnSnapshot;
  progress?: number | null;
  summary?: string | null;
  setComposerDraft: (text: string) => void;
}) {
  const [partyModalOpen, setPartyModalOpen] = useState(false);
  const s = snapshot;
  const meta = s.metadata ?? {};
  const chapterLine = [meta.chapter, meta.section].filter(Boolean).join(" · ");
  const showDescription = s.description && s.description !== s.narrative;

  let suggestedActions = meta.suggested_actions ?? [];
  if (s.intent?.toUpperCase() === "SETUP" && suggestedActions.length === 0) {
    suggestedActions = [
      "Lets start our adventure into the new world",
      "Tell me about the world",
      "Lets begin exploring",
    ];
  }

  return (
    <div className="flex h-full gap-4 overflow-hidden pr-2">
      {/* Left Column: Metadata & Actions */}
      <div className="overflow-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden flex w-1/3 flex-shrink-0 flex-col gap-6 overflow-y-auto pb-6">
        <header>
          {chapterLine && (
            <p className="font-rune text-xs uppercase tracking-widest text-parchment-dim">
              {chapterLine}
            </p>
          )}
          <div className="mt-1 flex items-center gap-3">
            <h2 className="text-gilded font-display text-3xl font-bold tracking-wide">
              {s.scene || "The scene unfolds"}
            </h2>
            <span className="rounded-full border border-gold/30 px-3 py-1 font-rune text-md text-gold whitespace-nowrap">
              {intentMeta(s.intent).icon} {intentMeta(s.intent).label}
            </span>
          </div>
          {typeof progress === "number" && (
            <div className="mt-3 flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-stone">
                <div
                  className="h-full bg-gold"
                  style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
                />
              </div>
              <span className="font-display text-[10px] text-parchment-dim">
                {Math.round(progress)}%
              </span>
            </div>
          )}
        </header>

        {summary && (
          <p className="border-l-2 border-gold/30 pl-3 font-body text-sm italic text-parchment-dim">
            {summary}
          </p>
        )}

        <Button variant="secondary" onClick={() => setPartyModalOpen(true)} className="w-full">
          View Party Details
        </Button>

        <SuggestionChips
          title="Suggested Actions"
          items={suggestedActions}
          onPick={setComposerDraft}
        />
        <SuggestionChips
          title="Where to next?"
          items={meta.next_scene_suggestions ?? []}
          onPick={setComposerDraft}
        />
      </div>

      {/* Right Column: Main Content */}
      <div className="overflow-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden flex flex-1 flex-col gap-6 overflow-y-auto border-l border-gold/20 pl-3 pb-6">
        <AssetGallery assets={meta.assets} alt={s.scene ?? "Scene"} />

        {showDescription && (
          <p className="font-body text-md leading-relaxed text-parchment-dim">
            {s.description}
          </p>
        )}
        {s.narrative && (
          <p className="font-body text-md leading-relaxed text-parchment">{s.narrative}</p>
        )}

        {s.dialogue && s.dialogue.length > 0 && (
          <section>
            <SectionLabel>Dialogue</SectionLabel>
            <DialogueBlock lines={s.dialogue} />
          </section>
        )}

        {meta.combat_log && meta.combat_log.length > 0 && (
          <section>
            <SectionLabel>Combat Log</SectionLabel>
            <CombatTable log={meta.combat_log} />
            {meta.math_breakdown && (
              <p className="mt-2 font-mono text-xs text-parchment-dim">{meta.math_breakdown}</p>
            )}
          </section>
        )}

        {s.initiative && s.initiative.length > 0 && (
          <section>
            <SectionLabel>Initiative</SectionLabel>
            <p className="font-body text-parchment">{s.initiative.join(" → ")}</p>
          </section>
        )}

        {meta.gm_notes && (
          <section className="parchment rounded-card border border-gold/30 p-4">
            <SectionLabel>GM Notes</SectionLabel>
            <p className="whitespace-pre-wrap font-body text-sm text-parchment-dim">
              {meta.gm_notes}
            </p>
          </section>
        )}
      </div>

      <Modal
        open={partyModalOpen}
        onClose={() => setPartyModalOpen(false)}
        title="Party Status"
        size="lg"
      >
        <PartyStatGrid party={s.party} />
      </Modal>
    </div>
  );
}

/**
 * The in-flight turn: the live trace while the Dungeon Master works, and the
 * draft once it pauses for approval. Shown in the reader so the GM watches the
 * scene take shape where the result will appear (req 1, req 5).
 */
function PendingView({
  events,
  awaiting,
  draft,
  onSync,
}: {
  events: SessionEvent[];
  awaiting: boolean;
  draft: string | null;
  onSync: () => void;
}) {
  const { setComposerDraft, approve, reject } = useConsole();
  const parsedDraft = awaiting && draft ? parseDraftToSnapshot(draft) : null;

  return (
    <div className="flex h-full flex-col gap-2">
      <header className="flex items-start justify-between">
        <div>
          <p className="font-display text-[10px] uppercase tracking-[0.3em] text-gold">
            {awaiting ? "" : "The Dungeon Master is at work"}
          </p>
          <h2 className="text-gilded mt-1 font-display text-2xl font-bold tracking-wide">
            {awaiting ? "" : "Weaving the scene…"}
          </h2>
        </div>
      </header>

      {awaiting && parsedDraft ? (
        <div className="parchment min-h-[300px] flex-1 overflow-hidden rounded-card border border-gold/40 p-4">
          <SnapshotLayout snapshot={parsedDraft} setComposerDraft={setComposerDraft} />
        </div>
      ) : awaiting && draft ? (
        <div className="parchment scroll-thin overflow-y-auto rounded-card border border-gold/40 p-4">
          <p className="whitespace-pre-wrap font-body text-parchment">{draft}</p>
        </div>
      ) : null}

      <div className="parchment scroll-thin overflow-y-auto rounded-card">
        {!awaiting && <>
          <Button onClick={onSync} className="float-right">
            Sync
          </Button>
          <EventTimeline events={events} running={!awaiting} />
        </>}
        {awaiting && (
          <div className="parchment flex justify-center">
            <ApprovalBar
              onApprove={approve}
              onReject={reject}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The scene/outcome reader — one component for both a clicked
 * historical turn and the just-completed outcome. Fed the active TurnSnapshot.
 */
export function SceneReaderPanel() {
  const {
    activeSnapshot,
    historyLoading,
    history,
    progress,
    summary,
    setComposerDraft,
    viewPending,
    runStatus,
    events,
    pendingDraft,
    streamDelaying,
    reconnectStream,
  } = useConsole();

  if (streamDelaying) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader label="Waking up the Dungeon Master…" />
      </div>
    );
  }

  // While a turn is in flight, the reader shows the live timeline / pending draft.
  if (viewPending) {
    return (
      <PendingView
        events={events}
        awaiting={runStatus === "awaiting_approval"}
        draft={pendingDraft}
        onSync={reconnectStream}
      />
    );
  }

  if (historyLoading && history.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader label="Reading the scene…" />
      </div>
    );
  }

  if (!activeSnapshot) {
    return (
      <div className="flex h-full items-center justify-center text-center">
        <div className="parchment max-w-md rounded-card border border-gold/30 p-8">
          <p className="font-display text-[10px] uppercase tracking-[0.3em] text-gold">
            The table is set
          </p>
          <h2 className="text-gilded mt-3 font-display text-3xl font-bold tracking-wide">
            Your adventure awaits
          </h2>
          <p className="mt-3 font-rune text-parchment-dim">
            Issue your first command to the Dungeon Master, and the unfolding scene
            will appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <SnapshotLayout
      snapshot={activeSnapshot}
      progress={progress}
      summary={summary}
      setComposerDraft={setComposerDraft}
    />
  );
}
