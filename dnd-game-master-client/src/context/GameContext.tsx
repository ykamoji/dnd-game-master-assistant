"use client";

import {
  createContext,
  useContext,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import { PRELOAD_PARTY } from "@/lib/games";
import type { PartyMember } from "@/lib/types";

// ---------------------------------------------------------------------------
// Step machine
// ---------------------------------------------------------------------------
export type Step =
  | "start"
  | "campaignSelect"
  | "partySelect"
  | "resumeLoad"
  | "console";

export type Branch = "new" | "resume" | null;

const STEPS: Record<Exclude<Branch, null> | "none", Step[]> = {
  none: ["start"],
  new: ["start", "campaignSelect", "partySelect", "console"],
  resume: ["start", "resumeLoad", "console"],
};

export function stepsFor(branch: Branch): Step[] {
  return STEPS[branch ?? "none"];
}

// ---------------------------------------------------------------------------
// State + actions
// ---------------------------------------------------------------------------
export interface GameState {
  branch: Branch;
  stepIndex: number;
  selectedGameId: string | null;
  party: PartyMember[];
  selectedCampaignId: string | null;
  /** The active ADK session/campaign id (new uuid for new, saved id for resume). */
  campaignId: string | null;
  /** Set when a new campaign is confirmed: the console fires its first turn. */
  autoStart: boolean;
  dissolving: boolean;
  assembling: boolean;
}

export const initialGameState: GameState = {
  branch: null,
  stepIndex: 0,
  selectedGameId: null,
  party: [],
  selectedCampaignId: null,
  campaignId: null,
  autoStart: false,
  dissolving: false,
  assembling: false,
};

export type GameAction =
  | { type: "CHOOSE_BRANCH"; branch: Exclude<Branch, null> }
  | { type: "NEXT" }
  | { type: "PREV" }
  | { type: "GO_TO"; index: number }
  | { type: "SELECT_GAME"; gameId: string }
  | { type: "SET_PARTY"; party: PartyMember[] }
  | { type: "PRELOAD_PARTY" }
  | { type: "SELECT_CAMPAIGN"; campaignId: string }
  | { type: "BEGIN_NEW_CAMPAIGN" }
  | { type: "CONSUME_AUTOSTART" }
  | { type: "START_DISSOLVE" }
  | { type: "FINISH_DISSOLVE" }
  | { type: "FINISH_ASSEMBLE" };

const clamp = (i: number, max: number) => Math.max(0, Math.min(i, max));
const newId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);

export function gameReducer(state: GameState, action: GameAction): GameState {
  const steps = stepsFor(state.branch);
  const lastIndex = steps.length - 1;

  switch (action.type) {
    case "CHOOSE_BRANCH": {
      const next = stepsFor(action.branch);
      return { ...state, branch: action.branch, stepIndex: clamp(1, next.length - 1) };
    }
    case "NEXT":
      return { ...state, stepIndex: clamp(state.stepIndex + 1, lastIndex) };
    case "PREV": {
      const idx = clamp(state.stepIndex - 1, lastIndex);
      // Returning to the start view resets the chosen branch so it can be re-picked.
      return idx === 0
        ? { ...state, stepIndex: 0, branch: null }
        : { ...state, stepIndex: idx };
    }
    case "GO_TO":
      return { ...state, stepIndex: clamp(action.index, lastIndex) };
    case "SELECT_GAME":
      // Lock in the campaign and advance (fade) to party selection.
      return {
        ...state,
        selectedGameId: action.gameId,
        stepIndex: clamp(state.stepIndex + 1, lastIndex),
      };
    case "SET_PARTY":
      return { ...state, party: action.party };
    case "PRELOAD_PARTY":
      return {
        ...state,
        party: PRELOAD_PARTY.map((m) => ({ ...m, id: newId() })),
      };
    case "SELECT_CAMPAIGN":
      // Resume: the saved id is also the active session id.
      return {
        ...state,
        selectedCampaignId: action.campaignId,
        campaignId: action.campaignId,
        autoStart: false,
      };
    case "BEGIN_NEW_CAMPAIGN":
      // Confirm & Begin: mint the session id, kick off the dissolve, and flag the
      // console to fire the first (party-setup) turn.
      return { ...state, campaignId: newId(), autoStart: true, dissolving: true };
    case "CONSUME_AUTOSTART":
      return { ...state, autoStart: false };
    case "START_DISSOLVE":
      return { ...state, dissolving: true };
    case "FINISH_DISSOLVE":
      // Dissolve always lands on the console (last step of either branch), which
      // then assembles itself in from the same drifting particles.
      return {
        ...state,
        dissolving: false,
        assembling: true,
        stepIndex: lastIndex,
      };
    case "FINISH_ASSEMBLE":
      return { ...state, assembling: false };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------
interface GameContextValue {
  state: GameState;
  dispatch: Dispatch<GameAction>;
  steps: Step[];
  currentStep: Step;
}

const GameContext = createContext<GameContextValue | null>(null);

export function GameProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(gameReducer, initialGameState);
  const steps = stepsFor(state.branch);
  const currentStep = steps[clamp(state.stepIndex, steps.length - 1)];
  return (
    <GameContext.Provider value={{ state, dispatch, steps, currentStep }}>
      {children}
    </GameContext.Provider>
  );
}

export function useGame(): GameContextValue {
  const ctx = useContext(GameContext);
  if (!ctx) throw new Error("useGame must be used within a GameProvider");
  return ctx;
}
