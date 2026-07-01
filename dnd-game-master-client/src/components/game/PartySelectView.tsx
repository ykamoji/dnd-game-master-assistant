"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { Loader } from "@/components/ui/Loader";
import { SectionShell } from "@/components/ui/SectionShell";
import { ClassDnaProfile } from "./ClassDnaProfile";
import { PartyMemberRow } from "./PartyMemberRow";
import { useGame } from "@/context/GameContext";
import { useClasses } from "@/hooks/useClasses";
import type { PartyMember } from "@/lib/types";

const MAX_PARTY = 6;
const newId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);

const emptyMember = (): PartyMember => ({
  id: newId(),
  name: "",
  className: "",
  role: "",
});

/** New-campaign step 2: assemble the party, then dissolve into the console. */
export function PartySelectView() {
  const { state, dispatch } = useGame();
  const { classes, loading, error } = useClasses();
  const [dnaClass, setDnaClass] = useState<string | null>(null);

  const party = state.party.length ? state.party : [emptyMember()];

  const setParty = (next: PartyMember[]) =>
    dispatch({ type: "SET_PARTY", party: next });

  const updateMember = (m: PartyMember) =>
    setParty(party.map((p) => (p.id === m.id ? m : p)));

  const removeMember = (id: string) =>
    setParty(party.filter((p) => p.id !== id));

  const addMember = () => {
    if (party.length < MAX_PARTY) setParty([...party, emptyMember()]);
  };

  const atMax = party.length >= MAX_PARTY;
  const canConfirm =
    party.length > 0 && party.every((p) => p.name.trim() && p.className);

  const dnaProfile = classes.find((c) => c.name === dnaClass);

  return (
    <SectionShell align="start">
      <div className="mb-5 text-center">
        <h2 className="text-gilded font-display text-3xl font-bold tracking-wide sm:text-4xl">
          Assemble Your Party
        </h2>
        <p className="mt-2 font-rune text-parchment-dim">
          Name your heroes, choose a class, and pick an archetype role — up to six.
        </p>
      </div>

      {loading && (
        <div className="flex justify-center py-12">
          <Loader label="Consulting the tomes…" />
        </div>
      )}
      {error && (
        <p className="text-center text-blood-bright">
          Could not load classes: {error}
        </p>
      )}

      {!loading && !error && (
        <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          {/* Left: party builder — rows pile downward, no inner scroll */}
          <div className="flex flex-col gap-3">
            <AnimatePresence initial={false}>
              {party.map((m) => (
                <motion.div
                  key={m.id}
                  layout
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ type: "spring", stiffness: 300, damping: 26 }}
                >
                  <PartyMemberRow
                    member={m}
                    classes={classes}
                    activeDna={dnaClass}
                    onChange={updateMember}
                    onRemove={() => removeMember(m.id)}
                    onViewDna={setDnaClass}
                  />
                </motion.div>
              ))}
            </AnimatePresence>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
              <Button variant="secondary" onClick={addMember} disabled={atMax}>
                + Add Hero
              </Button>
              <Button
                className="relative"
                variant="ghost"
                onClick={() => dispatch({ type: "PRELOAD_PARTY" })}
              >
                <div className="absolute left-1 text-[45px]">⚔</div> <div className="pl-5">Load Best Party</div>
              </Button>
              <Button
                onClick={() => dispatch({ type: "BEGIN_NEW_CAMPAIGN" })}
                disabled={!canConfirm}
                className=""
              >
                Confirm &amp; Begin
              </Button>
            </div>
            {atMax && (
              <p className="font-rune text-xs text-parchment-dim">
                A party may hold at most {MAX_PARTY} heroes.
              </p>
            )}
          </div>

          {/* Right: DNA profile panel (placeholder until a class is inspected) */}
          <aside className="parchment scroll-thin max-h-[68vh] self-start overflow-y-auto rounded-card border border-gold/30 p-6">
            {dnaProfile ? (
              <ClassDnaProfile profile={dnaProfile} />
            ) : (
              <DnaPlaceholder />
            )}
          </aside>
        </div>
      )}
    </SectionShell>
  );
}

/** Default right-panel content shown before any DNA profile is opened. */
function DnaPlaceholder() {
  return (
    <div className="space-y-4">
      <h3 className="text-gilded font-display text-xl font-bold tracking-wide">
        Character DNA Profiles
      </h3>
      <p className="text-sm leading-relaxed text-parchment-dim">
        Every hero is defined by a <span className="text-gold-bright">class</span>{" "}
        — its hit dice, proficiencies, and how it carries the party: martial
        strikers, divine healers, arcane controllers, and cunning skirmishers.
      </p>
      <p className="text-sm leading-relaxed text-parchment-dim">
        A <span className="text-gold-bright">role</span> is the class&apos;s
        archetype — its specialization. Choose the one that matches how you want
        to play that hero.
      </p>
      <p className="rounded-md border border-gold/20 bg-obsidian-2/60 p-3 text-sm text-parchment">
        Click a hero&apos;s <span className="text-gold">DNA</span> button to study
        that class&apos;s full profile right here.
      </p>
    </div>
  );
}
