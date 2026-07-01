"use client";

import { type ReactNode } from "react";

interface SectionShellProps {
  children: ReactNode;
  className?: string;
  /** Vertical alignment of the content within the viewport-height section. */
  align?: "center" | "start";
}

/**
 * Full-viewport wrapper for a single game-stage view. Sizes to the stage
 * height; the stage handles vertical translation. Use align="start" for views
 * whose content grows downward (e.g. a party list) so the top stays visible.
 */
export function SectionShell({
  children,
  className = "",
  align = "center",
}: SectionShellProps) {
  return (
    <section
      className={`flex h-screen w-full shrink-0 flex-col items-center overflow-y-auto overflow-x-hidden px-6 py-16 ${align === "start" ? "justify-start" : "justify-center"
        } ${className}`}
    >
      <div className="w-full">{children}</div>
    </section>
  );
}
