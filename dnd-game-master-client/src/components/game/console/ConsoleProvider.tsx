"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import {
  sendDecision,
  sessionStreamUrl,
  submitTurn as submitTurnApi,
} from "@/lib/api";
import type { SessionEvent, TurnSnapshot } from "@/lib/types";
import { useGame } from "@/context/GameContext";
import { GAME_CATALOG } from "@/lib/games";
import { extractDraft, isApprovalEvent } from "./events";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export type RunStatus =
  | "idle"
  | "running"
  | "awaiting_approval"
  | "rejecting"
  | "error";

/** Optional dice results to fold into the submitted command. */
export interface DiceRolls {
  d20?: number | null;
  d100?: number | null;
}

interface ConsoleState {
  activeIndex: number; // index into history (the persisted turns)
  /** When true, the reader/map show the in-flight turn instead of a snapshot. */
  viewPending: boolean;
  runStatus: RunStatus;
  events: SessionEvent[];
  pendingDraft: string | null;
  composerDraft: string;
  error: string | null;
  streamDelaying: boolean;
}

const initialState: ConsoleState = {
  activeIndex: -1,
  viewPending: false,
  runStatus: "idle",
  events: [],
  pendingDraft: null,
  composerDraft: "",
  error: null,
  streamDelaying: false,
};

type Action =
  | { type: "SELECT_TURN"; index: number }
  | { type: "SELECT_PENDING" }
  | { type: "SET_COMPOSER"; text: string }
  | { type: "RUN_START" }
  | { type: "RESUME_RUN" }
  | { type: "APPEND_EVENT"; event: SessionEvent }
  | { type: "CLEAR_EVENTS" }
  | { type: "AWAIT_APPROVAL"; draft: string }
  | { type: "RUN_DONE" }
  | { type: "REJECTING" }
  | { type: "REJECTED" }
  | { type: "RUN_ERROR"; message: string }
  | { type: "START_STREAM_DELAY" }
  | { type: "END_STREAM_DELAY" };

function reducer(state: ConsoleState, action: Action): ConsoleState {
  switch (action.type) {
    case "SELECT_TURN":
      return { ...state, activeIndex: action.index, viewPending: false };
    case "SELECT_PENDING":
      return { ...state, viewPending: true };
    case "SET_COMPOSER":
      return { ...state, composerDraft: action.text };
    case "RUN_START":
      return {
        ...state,
        runStatus: "running",
        viewPending: true,
        events: [],
        pendingDraft: null,
        error: null,
      };
    case "RESUME_RUN":
      return { ...state, runStatus: "running", viewPending: true, pendingDraft: null };
    case "APPEND_EVENT":
      if (state.events.some((e) => e.id === action.event.id)) return state;
      return { ...state, events: [...state.events, action.event] };
    case "CLEAR_EVENTS":
      return { ...state, events: [] };
    case "AWAIT_APPROVAL":
      return {
        ...state,
        runStatus: "awaiting_approval",
        viewPending: true,
        pendingDraft: action.draft,
      };
    case "RUN_DONE":
      return { ...state, runStatus: "idle", viewPending: false, events: [], pendingDraft: null };
    case "REJECTING":
      return { ...state, runStatus: "rejecting", pendingDraft: null };
    case "REJECTED":
      return {
        ...state,
        runStatus: "idle",
        viewPending: false,
        events: [],
        pendingDraft: null,
      };
    case "RUN_ERROR":
      return { ...state, runStatus: "error", viewPending: false, error: action.message };
    case "START_STREAM_DELAY":
      return { ...state, streamDelaying: true };
    case "END_STREAM_DELAY":
      return { ...state, streamDelaying: false };
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------
interface ConsoleContextValue {
  campaignId: string | null;
  campaignName: string;
  history: TurnSnapshot[];
  historyLoading: boolean;
  progress: number | null;
  summary: string | null;
  activeIndex: number;
  activeSnapshot: TurnSnapshot | null;
  /** A turn is in flight (running / awaiting approval / rejecting). */
  pending: boolean;
  /** The reader/map should display the in-flight turn rather than a snapshot. */
  viewPending: boolean;
  runStatus: RunStatus;
  events: SessionEvent[];
  pendingDraft: string | null;
  composerDraft: string;
  error: string | null;
  streamDelaying: boolean;
  submitTurn: (args: { text: string; dice?: DiceRolls }) => void;
  approve: () => void;
  reject: () => void;
  reconnectStream: () => void;
  selectTurn: (index: number) => void;
  selectPending: () => void;
  setComposerDraft: (text: string) => void;
}

const ConsoleContext = createContext<ConsoleContextValue | null>(null);

function formatDice(dice?: DiceRolls): string {
  if (!dice) return "";
  const parts: string[] = [];
  if (dice.d20 != null) parts.push(`d20=${dice.d20}`);
  if (dice.d100 != null) parts.push(`d100=${dice.d100}`);
  return parts.length ? `(rolled ${parts.join(", ")})` : "";
}

// The ambient POST runs the entire turn synchronously server-side and can
// legitimately take a while (multiple agent/tool calls). A dev proxy or flaky
// connection can drop the response long before the backend is done — but the
// backend keeps working and the SSE keeps streaming. This is how long we keep
// watching for the real outcome before giving up.
const OUTCOME_GRACE_MS = 90_000;
const OUTCOME_RECHECK_MS = 1_500;
// On a fresh mount, how long to watch the stream for an already-paused approval
// before concluding the session is settled and dropping the stream.
const RESTORE_PROBE_MS = 4_000;

interface ConsoleProviderProps {
  history: TurnSnapshot[];
  historyLoading: boolean;
  progress: number | null;
  summary: string | null;
  reloadHistory: () => void;
  campaignId: string | null;
  children: ReactNode;
}

/**
 * Owns ALL shared console state and the run lifecycle: submit a turn via the
 * ambient Pub/Sub endpoint, stream the session events over SSE for the live
 * trace + HITL pause, then approve/reject through /run. Feature panels are pure
 * consumers, so every layout behaves identically.
 */
export function ConsoleProvider({
  history,
  historyLoading,
  progress,
  summary,
  reloadHistory,
  campaignId,
  children,
}: ConsoleProviderProps) {
  const { state: game, dispatch: gameDispatch } = useGame();
  const [state, dispatch] = useReducer(reducer, initialState);

  // The session id is the campaign id (the ambient handler keys the session by
  // the Pub/Sub subscription, which we set to the campaign id).
  const userIdRef = useRef<string>("");
  if (!userIdRef.current) userIdRef.current = "user";

  const statusRef = useRef<RunStatus>("idle");
  const pendingRef = useRef(false);
  const historyRef = useRef(history);
  // Live event stream state (kept in refs so the EventSource callback is current).
  const esRef = useRef<EventSource | null>(null);
  const eventsRef = useRef<SessionEvent[]>([]);
  const seenRef = useRef<Set<string>>(new Set());
  // Which campaign id has already auto-started, so it fires exactly once.
  const autoStartedForRef = useRef<string | null>(null);

  useEffect(() => {
    historyRef.current = history;
  }, [history]);
  useEffect(() => {
    statusRef.current = state.runStatus;
    pendingRef.current = state.runStatus !== "idle" && state.runStatus !== "error";
  }, [state.runStatus]);

  // When persisted history grows (initial load or a completed turn), snap the
  // reader to the newest turn — unless a turn is in flight (keep the pending view).
  useEffect(() => {
    if (history.length && !pendingRef.current) {
      dispatch({ type: "SELECT_TURN", index: history.length - 1 });
    }
  }, [history.length]);

  const campaignName = useMemo(() => {
    const entry = GAME_CATALOG.find((g) => g.id === game.selectedGameId);
    return entry?.title ?? game.selectedGameId ?? campaignId ?? "the adventure";
  }, [game.selectedGameId, campaignId]);

  const bootstrapPreamble = useCallback(() => {
    const roster = game.party
      .filter((p) => p.name.trim())
      .map((p) => `${p.name} the ${p.role || p.className} (${p.className})`)
      .join("; ");
    return `[New campaign] Adventure: "${campaignName}". Party: ${roster || "to be determined"
      }. Set up the campaign and party, then begin:`;
  }, [game.party, campaignName]);

  const closeStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const resetEvents = useCallback(() => {
    eventsRef.current = [];
    seenRef.current = new Set();
  }, []);

  // Open the SSE event stream for a session. Each frame is one SessionEvent; we
  // append it (dedup by id) and, when the HITL pause arrives, surface the draft
  // and close the stream — the run is parked until the GM decides.
  const openStream = useCallback(
    (sid: string) => {
      closeStream();
      const es = new EventSource(sessionStreamUrl(sid));
      esRef.current = es;
      es.onmessage = (e) => {
        let ev: SessionEvent;
        try {
          ev = JSON.parse(e.data) as SessionEvent;
        } catch {
          return;
        }
        if (!ev?.id || seenRef.current.has(ev.id)) return;
        seenRef.current.add(ev.id);
        eventsRef.current = [...eventsRef.current, ev];
        dispatch({ type: "APPEND_EVENT", event: ev });
        
        // If it's a HITL approval pause
        if (isApprovalEvent(ev)) {
          statusRef.current = "awaiting_approval";
          dispatch({ type: "AWAIT_APPROVAL", draft: extractDraft(eventsRef.current) });
          closeStream(); // run is paused at the gate — stop streaming
        } 
        // If it's the final output event, the run is complete.
        // This avoids needing to continuously poll getCampaign in waitForOutcome.
        else if (ev.author === "output_agent" && ev.actions?.state_delta) {
           // We know the turn is finished. Call reloadHistory to update the UI.
           reloadHistory();
        }
      };
      // On a transient error EventSource auto-reconnects; the replay is deduped.
    },
    [closeStream],
  );

  /**
   * Wait for a submitted/resumed turn to reach its real outcome. The SSE drives
   * the UI live (trace + approval); this just resolves the action's promise:
   * the approval arriving flips status off "running", and a completed turn grows
   * the persisted history. Errors out only if neither happens in the grace window.
   */
  const waitForOutcome = useCallback(
    (startHistoryLen: number): Promise<void> =>
      new Promise((resolve) => {
        // We trigger a single reloadHistory to see if it's already done (e.g. submitTurnApi finished successfully).
        reloadHistory();

        const deadline = Date.now() + OUTCOME_GRACE_MS;
        const check = () => {
          if (statusRef.current !== "running") {
            resolve(); // the SSE already settled this (approval / error)
            return;
          }
          if (historyRef.current.length > startHistoryLen) {
            closeStream();
            statusRef.current = "idle";
            dispatch({ type: "RUN_DONE" });
            dispatch({ type: "SELECT_TURN", index: historyRef.current.length - 1 });
            resolve();
            return;
          }
          if (Date.now() >= deadline) {
            closeStream();
            statusRef.current = "error";
            dispatch({
              type: "RUN_ERROR",
              message:
                "Lost contact while this turn was processing. It may still finish in the background — try again in a moment.",
            });
            resolve();
            return;
          }
          // Rely on SSE 'output_agent' event to trigger reloadHistory when the turn is actually done,
          // rather than continuously polling getCampaign and causing 404 spam.
          setTimeout(check, OUTCOME_RECHECK_MS);
        };
        check();
      }),
    [closeStream, reloadHistory],
  );

  const submitTurn = useCallback(
    async ({ text, dice }: { text: string; dice?: DiceRolls }) => {
      if (statusRef.current !== "idle" && statusRef.current !== "error") return;
      const action = [formatDice(dice), text.trim()].filter(Boolean).join(" ");
      if (!action) return;
      const sid = campaignId;
      if (!sid) {
        dispatch({ type: "RUN_ERROR", message: "No campaign selected" });
        return;
      }
      const isFirstNewTurn = game.branch === "new" && historyRef.current.length === 0;
      const finalAction = isFirstNewTurn ? `${bootstrapPreamble()} ${action}` : action;
      const startLen = historyRef.current.length;

      statusRef.current = "running";
      dispatch({ type: "RUN_START" });
      resetEvents();

      dispatch({ type: "START_STREAM_DELAY" });
      setTimeout(() => {
        if (statusRef.current === "running") {
          dispatch({ type: "END_STREAM_DELAY" });
          openStream(sid);
        }
      }, 5000);

      // The POST may resolve or fail in transit; either way the SSE + history
      // tell us the real outcome.
      await submitTurnApi({
        sessionId: sid,
        userId: userIdRef.current,
        data: { action: finalAction },
      }).catch(() => undefined);
      await waitForOutcome(startLen);
    },
    [campaignId, game.branch, bootstrapPreamble, openStream, resetEvents, waitForOutcome],
  );

  /**
   * Fire the first turn of a new campaign — triggered by "Confirm & Begin" in the
   * party selector (via the GameContext autoStart flag). The payload carries the
   * chosen adventure + assembled party as JSON so the setup agent can build the
   * campaign. Managed here (not from the party view) so the live timeline and
   * approval gate work exactly like any other turn.
   */
  const beginCampaign = useCallback(
    async (sid: string) => {
      const partyPayload = game.party
        .filter((p) => p.name.trim())
        .map((p) => ({ role: p.role, class: p.className, name: p.name }));
      const startLen = historyRef.current.length;

      statusRef.current = "running";
      dispatch({ type: "RUN_START" });
      resetEvents();

      dispatch({ type: "START_STREAM_DELAY" });
      setTimeout(() => {
        if (statusRef.current === "running") {
          dispatch({ type: "END_STREAM_DELAY" });
          openStream(sid);
        }
      }, 5000);

      await submitTurnApi({
        sessionId: sid,
        userId: userIdRef.current,
        data: { game: campaignName, party: partyPayload },
      }).catch(() => undefined);
      await waitForOutcome(startLen);
    },
    [game.party, campaignName, openStream, resetEvents, waitForOutcome],
  );

  const approve = useCallback(async () => {
    if (statusRef.current !== "awaiting_approval" || !campaignId) return;
    const startLen = historyRef.current.length;
    statusRef.current = "running";
    dispatch({ type: "RESUME_RUN" });
    console.log(campaignId)
    openStream(campaignId); // stream the continuation (replayed events are deduped)
    await sendDecision({ sessionId: campaignId, userId: userIdRef.current, approved: true }).catch(
      () => undefined,
    );
    await waitForOutcome(startLen);
  }, [campaignId, openStream, waitForOutcome]);

  const reject = useCallback(async () => {
    if (statusRef.current !== "awaiting_approval" || !campaignId) return;
    statusRef.current = "rejecting";
    closeStream();
    dispatch({ type: "REJECTING" });
    try {
      await sendDecision({ sessionId: campaignId, userId: userIdRef.current, approved: false });
    } catch {
      // Non-fatal: the turn isn't persisted on rejection anyway.
    }
    statusRef.current = "idle";
    dispatch({ type: "REJECTED" });
    dispatch({ type: "SELECT_TURN", index: historyRef.current.length - 1 });
  }, [campaignId, closeStream]);

  const reconnectStream = useCallback(() => {
    if (campaignId) {
      openStream(campaignId);
    }
  }, [campaignId, openStream]);

  const selectTurn = useCallback((index: number) => {
    dispatch({ type: "SELECT_TURN", index });
  }, []);
  const selectPending = useCallback(() => {
    dispatch({ type: "SELECT_PENDING" });
  }, []);
  const setComposerDraft = useCallback((text: string) => {
    dispatch({ type: "SET_COMPOSER", text });
  }, []);

  // On fresh mount, probe the stream: if the session is already paused at the
  // HITL gate, the replayed approval event restores the approval bar. If nothing
  // is pending within the probe window, drop the stream (settled session).
  useEffect(() => {
    if (!campaignId) return;
    if (game.autoStart) return; // a fresh new campaign auto-starts below instead
    resetEvents();
    openStream(campaignId);
    const probe = setTimeout(() => {
      if (statusRef.current === "idle") {
        closeStream();
        dispatch({ type: "CLEAR_EVENTS" });
      }
    }, RESTORE_PROBE_MS);
    return () => {
      clearTimeout(probe);
      closeStream();
    };
  }, [campaignId, game.autoStart, openStream, closeStream, resetEvents]);

  // "Confirm & Begin" fires the first turn once per new campaign.
  useEffect(() => {
    if (
      game.autoStart &&
      campaignId &&
      autoStartedForRef.current !== campaignId &&
      statusRef.current === "idle"
    ) {
      autoStartedForRef.current = campaignId;
      gameDispatch({ type: "CONSUME_AUTOSTART" });
      void beginCampaign(campaignId);
    }
  }, [game.autoStart, campaignId, beginCampaign, gameDispatch]);

  const pending = state.runStatus !== "idle" && state.runStatus !== "error";
  const activeSnapshot =
    !state.viewPending && history.length
      ? history[Math.min(Math.max(state.activeIndex, 0), history.length - 1)]
      : null;

  const value: ConsoleContextValue = {
    campaignId,
    campaignName,
    history,
    historyLoading,
    progress,
    summary,
    activeIndex: state.activeIndex,
    activeSnapshot,
    pending,
    viewPending: state.viewPending,
    runStatus: state.runStatus,
    events: state.events,
    pendingDraft: state.pendingDraft,
    composerDraft: state.composerDraft,
    error: state.error,
    streamDelaying: state.streamDelaying,
    submitTurn,
    approve,
    reject,
    reconnectStream,
    selectTurn,
    selectPending,
    setComposerDraft,
  };

  return <ConsoleContext.Provider value={value}>{children}</ConsoleContext.Provider>;
}

export function useConsole(): ConsoleContextValue {
  const ctx = useContext(ConsoleContext);
  if (!ctx) throw new Error("useConsole must be used within a ConsoleProvider");
  return ctx;
}
