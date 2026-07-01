"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { DissolveOverlay } from "@/components/ui/DissolveOverlay";
import { NavButton } from "@/components/ui/NavButton";
import { useAssemble } from "@/hooks/useAssemble";
import { useGame, type Step } from "@/context/GameContext";
import { StartChoiceView } from "./StartChoiceView";
import { CampaignSelectView } from "./CampaignSelectView";
import { PartySelectView } from "./PartySelectView";
import { ResumeView } from "./ResumeView";
import { ConsoleView } from "./ConsoleView";
import { LandingView } from "@/components/landing/LandingView";

function renderStep(step: Step) {
  switch (step) {
    case "landing":
      return <LandingView />;
    case "start":
      return <StartChoiceView />;
    case "campaignSelect":
      return <CampaignSelectView />;
    case "partySelect":
      return <PartySelectView />;
    case "resumeLoad":
      return <ResumeView />;
    case "console":
      return <ConsoleView />;
  }
}

/**
 * Scroll-locked, Apple-style stage. Views are stacked vertically and revealed
 * by translating the stack; the user moves with the corner nav buttons (or
 * arrow keys). Forward-on-choice steps (start/campaign/party/resume) gate the
 * down button so the flow stays coherent.
 */
export function GameStage() {
  const { state, dispatch, steps, currentStep } = useGame();
  const { stepIndex, branch, selectedGameId, dissolving, assembling } = state;
  const activeViewRef = useRef<HTMLDivElement | null>(null);
  const nextViewRef = useRef<HTMLDivElement | null>(null);
  const router = useRouter();

  // Seamless dissolve → assemble: capture the next view up front, while the
  // outgoing dissolve is still playing, so assembly can start with no gap.
  const { canvasRef, prepare, run, cancel } = useAssemble();

  useEffect(() => {
    if (dissolving && nextViewRef.current) prepare(nextViewRef.current);
  }, [dissolving, prepare]);

  useEffect(() => {
    if (!assembling) {
      if (activeViewRef.current) activeViewRef.current.style.visibility = "";
      return;
    }
    let cancelled = false;
    (async () => {
      // If we arrived from the landing page, we need to capture the target now,
      // as it wasn't pre-captured during an outgoing dissolve.
      if (!dissolving && activeViewRef.current) {
        await prepare(activeViewRef.current);
      }
      await run();
      if (!cancelled) dispatch({ type: "FINISH_ASSEMBLE" });
    })();
    return () => {
      cancelled = true;
      cancel();
    };
  }, [assembling, run, cancel, dispatch]);

  // Suppress the slide animation while a dissolve resolves so the post-dissolve
  // jump to the console is instant (no scroll-down, no flash of the old view).
  const [animateSlide, setAnimateSlide] = useState(true);
  useEffect(() => {
    if (dissolving) {
      setAnimateSlide(false);
      return;
    }
    // Re-enable after the instant jump has committed.
    const id = requestAnimationFrame(() =>
      requestAnimationFrame(() => setAnimateSlide(true)),
    );
    return () => cancelAnimationFrame(id);
  }, [dissolving]);

  // A dissolved view is left visibility:hidden (DissolveOverlay never restores
  // it, to avoid flashing during the jump). Clear it once it becomes the active
  // step again — so it stays invisible while off-screen, but renders normally if
  // the player navigates back to it. The console is exempt: its visibility is
  // React-controlled below (hidden while assembling) so we don't fight it here.
  useEffect(() => {
    const el = activeViewRef.current;
    if (el && currentStep !== "console") el.style.visibility = "";
  }, [stepIndex, currentStep]);

  const lastIndex = steps.length - 1;

  // Up works everywhere. (Allow going back from console if desired).
  const canGoUp = !dissolving && !assembling;
  const canGoDown = (() => {
    if (dissolving || assembling || stepIndex >= lastIndex) return false;
    if (currentStep === "landing") return false; // Must explicitly click Enter the Table
    if (currentStep === "start") return branch !== null;
    if (currentStep === "campaignSelect") return Boolean(selectedGameId);
    // party + resume require an explicit action (confirm / select → dissolve).
    if (currentStep === "partySelect" || currentStep === "resumeLoad") return false;
    return true;
  })();

  const goUp = useCallback(() => {
    if (stepIndex > 0) dispatch({ type: "PREV" });
    else router.push("/"); // already at the first view → back to the landing page
  }, [stepIndex, dispatch, router]);
  const goDown = useCallback(() => dispatch({ type: "NEXT" }), [dispatch]);

  // Arrow keys mirror the nav buttons.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowUp" && canGoUp) goUp();
      if (e.key === "ArrowDown" && canGoDown) goDown();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canGoUp, canGoDown, goUp, goDown]);

  return (
    <div className="relative h-screen w-full overflow-hidden">
      {/* Black overlay for the initial capture so the target doesn't flash */}
      {assembling && !dissolving && (
        <div className="pointer-events-none fixed inset-0 z-40 bg-obsidian" />
      )}

      {/* Corner navigation (hidden on landing page) */}
      {currentStep !== "landing" && (
        <div className="pointer-events-none fixed inset-x-0 top-0 z-40 flex items-start justify-between p-4 sm:p-6">
          <div className="pointer-events-auto">
            <NavButton direction="up" label="Back" onClick={goUp} disabled={!canGoUp} />
          </div>
          <StepDots count={steps.length - 1} active={stepIndex - 1} />
          <div className="pointer-events-auto">
            <NavButton
              direction="down"
              label="Next"
              onClick={goDown}
              disabled={!canGoDown}
            />
          </div>
        </div>
      )}

      {/* Vertically translated stack of full-screen views */}
      <div
        className={`will-change-transform ${
          animateSlide
            ? "transition-transform duration-700 ease-[cubic-bezier(0.65,0,0.35,1)]"
            : ""
        }`}
        style={{ transform: `translateY(-${stepIndex * 100}vh)` }}
      >
        {steps.map((step, i) => (
          <div
            key={step}
            ref={(el) => {
              if (i === stepIndex) activeViewRef.current = el;
              if (i === stepIndex + 1) nextViewRef.current = el;
            }}
            className={`w-full ${step === "landing" ? "h-screen overflow-y-auto" : "h-screen overflow-hidden"}`}
          >
            {renderStep(step)}
          </div>
        ))}
      </div>

      <DissolveOverlay
        targetRef={activeViewRef}
        active={dissolving}
        onComplete={() => dispatch({ type: "FINISH_DISSOLVE" })}
      />
      {/* Assemble canvas — driven by the useAssemble hook (pre-captured during
          the dissolve for a seamless handoff). */}
      {assembling && (
        <canvas
          ref={canvasRef}
          className="pointer-events-none fixed inset-0 z-50"
          aria-hidden
        />
      )}
    </div>
  );
}

function StepDots({ count, active }: { count: number; active: number }) {
  return (
    <div className="pointer-events-none mt-3 flex gap-2">
      {Array.from({ length: count }).map((_, i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full transition-colors ${
            i === active ? "bg-gold" : "bg-parchment-dim/40"
          }`}
        />
      ))}
    </div>
  );
}
